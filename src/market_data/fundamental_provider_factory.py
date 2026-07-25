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

logger = logging.getLogger(__name__)

_cache_lock = asyncio.Lock()
_cached_provider: Optional[IFundamentalDataProvider] = None
_cached_provider_kind: Optional[str] = None
_cached_at: float = 0.0


async def get_fundamental_data_provider(force_refresh: bool = False) -> IFundamentalDataProvider:
    """Returns the IFundamentalDataProvider the caller should use right now."""
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

        provider, kind = await _select_provider()
        _cached_provider = provider
        _cached_provider_kind = kind
        _cached_at = now
        return provider


def get_last_selected_fundamental_provider_kind() -> Optional[str]:
    """"dev" | "sahmk" | None (nothing selected yet) -- for diagnostics."""
    return _cached_provider_kind


async def _select_provider() -> Tuple[IFundamentalDataProvider, str]:
    override = market_data_config.get_configured_provider_name()

    if override == "dev":
        logger.info("MARKET_DATA_PROVIDER=dev -- using DevFundamentalDataProvider (synthetic data).")
        return DevFundamentalDataProvider(), "dev"

    if override not in ("auto", "sahmk"):
        logger.warning("Unknown MARKET_DATA_PROVIDER=%r -- treating as 'auto'.", override)

    if not market_data_config.has_sahmk_credentials():
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

    provider = SahmkFundamentalDataProvider()
    try:
        reachable = await asyncio.wait_for(
            provider.authenticate(),
            timeout=market_data_config.get_provider_probe_timeout_seconds(),
        )
    except asyncio.TimeoutError:
        logger.warning(
            "SAHMK connectivity probe timed out -- falling back to DevFundamentalDataProvider "
            "(synthetic data) for this process."
        )
        await provider.disconnect()
        return DevFundamentalDataProvider(), "dev"
    except (SahmkError, CircuitBreakerOpenError) as exc:
        logger.warning(
            "SAHMK connectivity probe failed (%s) -- falling back to DevFundamentalDataProvider.",
            exc,
        )
        await provider.disconnect()
        return DevFundamentalDataProvider(), "dev"

    if not reachable:
        logger.warning(
            "SAHMK authentication check did not succeed -- falling back to "
            "DevFundamentalDataProvider (synthetic data)."
        )
        await provider.disconnect()
        return DevFundamentalDataProvider(), "dev"

    logger.info(
        "SAHMK is reachable and the configured API key was accepted -- "
        "using SahmkFundamentalDataProvider (live data)."
    )
    return provider, "sahmk"


def reset_fundamental_provider_cache() -> None:
    """Test-only: clears the cached provider selection."""
    global _cached_provider, _cached_provider_kind, _cached_at
    _cached_provider = None
    _cached_provider_kind = None
    _cached_at = 0.0
