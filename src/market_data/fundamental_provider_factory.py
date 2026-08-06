"""Selects the IFundamentalDataProvider the running process should use.

Mirrors src.market_data.provider_factory's design exactly -- same
selection policy, same environment variables, same "never fail to boot
over an unreachable vendor" guarantee -- for the fundamentals provider
instead of the market-data (OHLCV/quote) provider. Kept as a separate
module rather than folded into provider_factory.py because the two
provider families (IMarketDataProvider / IFundamentalDataProvider) are
already separate abstractions (M2.1 vs. M2.3) with separate factories;
this preserves that boundary instead of quietly merging them.

MARKET_DATA_PROVIDER (the same variable, not a separate
FUNDAMENTAL_DATA_PROVIDER) controls both selections -- there is exactly
one "am I allowed to call SAHMK" decision for a given deployment, not
one per data family.
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data import config as market_data_config
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider
from src.market_data.providers.fundamental_data_provider import IFundamentalDataProvider
from src.market_data.providers.sahmk_fundamental_data_provider import SahmkFundamentalDataProvider
from src.market_data.sahmk.exceptions import SahmkError
from src.market_data.strict_mode import StrictRealDataUnavailableError

logger = logging.getLogger(__name__)

_cache_lock = asyncio.Lock()
_cached_provider: Optional[IFundamentalDataProvider] = None
_cached_provider_kind: Optional[str] = None
_cached_at: float = 0.0


async def get_fundamental_data_provider(force_refresh: bool = False) -> IFundamentalDataProvider:
    """Returns the IFundamentalDataProvider the caller should use right now.

    Fundamentals-side twin of provider_factory.get_market_data_provider()
    -- see that function's docstring for the full rationale. A cache
    refresh reuses the previous SahmkFundamentalDataProvider instance
    (and its live aiohttp session) whenever it's still the right kind,
    instead of unconditionally closing it out from under a caller that
    might still be mid-request against it; a genuine kind change is
    disconnected with a grace delay rather than immediately.
    """
    global _cached_provider, _cached_provider_kind, _cached_at

    async with _cache_lock:
        cache_seconds = market_data_config.get_provider_selection_cache_seconds()
        now = time.monotonic()
        if (
            not force_refresh
            and _cached_provider is not None
            and cache_seconds > 0
            and (now - _cached_at) < cache_seconds
        ):
            return _cached_provider

        previous_provider = _cached_provider
        provider, kind = await _select_provider(previous_provider)

        if previous_provider is not None and previous_provider is not provider:
            _disconnect_with_grace(previous_provider)

        _cached_provider = provider
        _cached_provider_kind = kind
        _cached_at = now
        return provider


_pending_disconnects: "set[asyncio.Task]" = set()


def _disconnect_with_grace(provider: IFundamentalDataProvider) -> None:
    """Schedules a superseded provider's disconnect after a grace
    delay instead of closing it immediately -- see
    provider_factory._disconnect_with_grace()'s docstring for the full
    concurrency-bug rationale this mirrors."""

    async def _delayed_disconnect() -> None:
        try:
            await asyncio.sleep(market_data_config.get_provider_disconnect_grace_seconds())
            await provider.disconnect()
        except Exception:
            logger.warning("Error disconnecting a superseded fundamental data provider.", exc_info=True)

    task = asyncio.ensure_future(_delayed_disconnect())
    _pending_disconnects.add(task)
    task.add_done_callback(_pending_disconnects.discard)


def get_last_selected_fundamental_provider_kind() -> Optional[str]:
    """"dev" | "sahmk" | None (nothing selected yet) -- for diagnostics."""
    return _cached_provider_kind


async def _select_provider(
    previous_provider: Optional[IFundamentalDataProvider] = None,
) -> Tuple[IFundamentalDataProvider, str]:
    """See provider_factory._select_provider()'s docstring -- this
    mirrors it exactly, including reusing `previous_provider` (and its
    live aiohttp session) instead of constructing and swapping in a
    fresh SahmkFundamentalDataProvider whenever it's already the right
    kind."""
    override = market_data_config.get_configured_provider_name()
    strict = not market_data_config.is_synthetic_data_allowed()

    if override == "dev":
        if strict:
            raise StrictRealDataUnavailableError(
                "STRICT_REAL_DATA is enabled but MARKET_DATA_PROVIDER=dev explicitly "
                "requests synthetic data -- refusing to use DevFundamentalDataProvider."
            )
        logger.info("MARKET_DATA_PROVIDER=dev -- using DevFundamentalDataProvider (synthetic data).")
        return DevFundamentalDataProvider(), "dev"

    if override not in ("auto", "sahmk"):
        logger.warning("Unknown MARKET_DATA_PROVIDER=%r -- treating as 'auto'.", override)

    if not market_data_config.has_sahmk_credentials():
        if strict:
            raise StrictRealDataUnavailableError("SAHMK_API_KEY is not configured.")
        if override == "sahmk":
            logger.error(
                "MARKET_DATA_PROVIDER=sahmk but SAHMK_API_KEY is not configured -- "
                "falling back to DevFundamentalDataProvider."
            )
        else:
            logger.info(
                "SAHMK_API_KEY not configured -- using DevFundamentalDataProvider (synthetic data)."
            )
        return DevFundamentalDataProvider(), "dev"

    reused = isinstance(previous_provider, SahmkFundamentalDataProvider)
    provider = previous_provider if reused else SahmkFundamentalDataProvider()

    async def _cleanup_on_failure() -> None:
        if not reused:
            await provider.disconnect()

    try:
        reachable = await asyncio.wait_for(
            provider.authenticate(),
            timeout=market_data_config.get_provider_probe_timeout_seconds(),
        )
    except asyncio.TimeoutError:
        await _cleanup_on_failure()
        if strict:
            raise StrictRealDataUnavailableError("SAHMK connectivity probe timed out.")
        logger.warning(
            "SAHMK connectivity probe timed out -- falling back to DevFundamentalDataProvider "
            "(synthetic data) for this process."
        )
        return DevFundamentalDataProvider(), "dev"
    except (SahmkError, CircuitBreakerOpenError) as exc:
        await _cleanup_on_failure()
        if strict:
            raise StrictRealDataUnavailableError(f"SAHMK connectivity probe failed: {exc}")
        logger.warning(
            "SAHMK connectivity probe failed (%s) -- falling back to DevFundamentalDataProvider.",
            exc,
        )
        return DevFundamentalDataProvider(), "dev"

    if not reachable:
        await _cleanup_on_failure()
        if strict:
            raise StrictRealDataUnavailableError("SAHMK authentication check did not succeed.")
        logger.warning(
            "SAHMK authentication check did not succeed -- falling back to "
            "DevFundamentalDataProvider (synthetic data)."
        )
        return DevFundamentalDataProvider(), "dev"

    logger.info(
        "SAHMK is reachable and the configured API key was accepted -- using "
        "%s SahmkFundamentalDataProvider (live data).",
        "the existing" if reused else "a new",
    )
    return provider, "sahmk"


def reset_fundamental_provider_cache() -> None:
    """Test-only: clears the cached provider selection."""
    global _cached_provider, _cached_provider_kind, _cached_at
    _cached_provider = None
    _cached_provider_kind = None
    _cached_at = 0.0
