"""Selects the IMarketDataProvider the running process should use.

Default ("auto", MARKET_DATA_PROVIDER unset): if SAHMK_API_KEY is
configured, this probes SAHMK's cheapest confirmed endpoint
(GET /market/summary/, via SahmkMarketDataProvider.authenticate()) with
a short timeout. If that succeeds -- including the case where the key
is valid but plan-limited (SahmkEntitlementError, still counted as
"authenticated" by the provider) -- the real SahmkMarketDataProvider is
returned. Any connectivity failure (DNS, connection refused/reset,
timeout, an egress-policy block -- exactly the class of failure this
platform's own sandboxed environments can produce) or authentication
failure falls back to DevMarketDataProvider, logged clearly, so the
application never fails to start merely because SAHMK happens to be
unreachable from wherever it is currently running. Point 8 of the SAHMK
integration requirement ("automatically use the real API whenever it
runs in an environment that has network access") is implemented here,
and only here -- every other module in this package is unaware of
network availability and simply implements IMarketDataProvider.

MARKET_DATA_PROVIDER can force "dev" (always synthetic, e.g. for CI) or
"sahmk" (always attempt live, still falling back to "dev" on an
unreachable host -- booting must never depend on live third-party
network access). Selection is cached for
MARKET_DATA_PROVIDER_CACHE_SECONDS (default 60s) so a tight ingestion
loop does not re-probe connectivity on every call.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data import config as market_data_config
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkError
from src.market_data.strict_mode import StrictRealDataUnavailableError

logger = logging.getLogger(__name__)

_cache_lock = asyncio.Lock()
_cached_provider: Optional[IMarketDataProvider] = None
_cached_provider_kind: Optional[str] = None
_cached_at: float = 0.0

# In-process only (resets on restart -- disclosed, not a persisted
# audit trail): the outcome of the most recent *actual* selection
# attempt (i.e. excluding cache hits, which don't re-probe anything),
# for GET /health/market-data. "SUCCESS" means a real SahmkMarketData
# Provider was selected; "FAILED" covers every other outcome (SAHMK
# unreachable/rejected -- whether that resulted in a synthetic
# fallback or, under strict mode, a raised
# StrictRealDataUnavailableError).
_last_connectivity_status: Optional[str] = None
_last_connectivity_at: Optional[datetime] = None
_last_real_data_at: Optional[datetime] = None


def get_market_data_health() -> dict:
    """Secret-free snapshot for GET /health/market-data. Never touches
    the network itself -- reports the outcome of whatever the most
    recent real selection attempt (by any caller) already found."""
    return {
        "configured_provider": market_data_config.get_configured_provider_name(),
        "strict_real_data": market_data_config.is_strict_real_data_enabled(),
        "synthetic_allowed": market_data_config.is_synthetic_data_allowed(),
        "sahmk_key_present": market_data_config.has_sahmk_credentials(),
        "current_provider_kind": _cached_provider_kind,
        "last_connectivity_status": _last_connectivity_status,
        "last_connectivity_at": _last_connectivity_at.isoformat() if _last_connectivity_at else None,
        "last_real_data_at": _last_real_data_at.isoformat() if _last_real_data_at else None,
    }


async def get_market_data_provider(force_refresh: bool = False) -> IMarketDataProvider:
    """Returns the IMarketDataProvider the caller should use right now.

    Any provider this call replaces (cache expiry or force_refresh=True)
    is disconnected before the new one is installed -- a live
    SahmkMarketDataProvider holds an open aiohttp session, and simply
    overwriting the cached reference without closing it leaks that
    session every MARKET_DATA_PROVIDER_CACHE_SECONDS. Disconnecting
    happens while still holding _cache_lock, so it's strictly ordered
    against the new selection and can't race a second concurrent
    refresh. Trade-off, disclosed rather than engineered around with a
    full reference-counted drain: a caller that fetched the outgoing
    provider an instant before this runs and is still mid-request
    against it could see that request fail if disconnect() closes the
    underlying session out from under it. This was judged an acceptable,
    narrow risk against the alternative (a guaranteed, unbounded leak) --
    cache refreshes are infrequent (default every 60s) and callers are
    expected to fetch-and-use the provider promptly, not hold it across
    a refresh boundary.
    """
    global _cached_provider, _cached_provider_kind, _cached_at
    global _last_connectivity_status, _last_connectivity_at, _last_real_data_at

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
        try:
            provider, kind = await _select_provider()
        except StrictRealDataUnavailableError:
            _last_connectivity_status = "FAILED"
            _last_connectivity_at = datetime.now(timezone.utc)
            raise

        _last_connectivity_status = "SUCCESS" if kind == "sahmk" else "FAILED"
        _last_connectivity_at = datetime.now(timezone.utc)
        if kind == "sahmk":
            _last_real_data_at = _last_connectivity_at

        if previous_provider is not None and previous_provider is not provider:
            await _disconnect_quietly(previous_provider)

        _cached_provider = provider
        _cached_provider_kind = kind
        _cached_at = now
        return provider


async def _disconnect_quietly(provider: IMarketDataProvider) -> None:
    """Disconnects a superseded provider. Never lets a disconnect
    failure prevent the new selection from being installed -- a
    same-process resource-cleanup problem must not be allowed to break
    provider selection itself."""
    try:
        await provider.disconnect()
    except Exception:
        logger.warning("Error disconnecting a superseded market data provider.", exc_info=True)


def get_last_selected_provider_kind() -> Optional[str]:
    """"dev" | "sahmk" | None (nothing selected yet) -- for diagnostics
    (e.g. a status endpoint) without exposing any credential."""
    return _cached_provider_kind


async def _select_provider() -> Tuple[IMarketDataProvider, str]:
    override = market_data_config.get_configured_provider_name()
    strict = not market_data_config.is_synthetic_data_allowed()

    if override == "dev":
        if strict:
            raise StrictRealDataUnavailableError(
                "STRICT_REAL_DATA is enabled but MARKET_DATA_PROVIDER=dev explicitly "
                "requests synthetic data -- refusing to use DevMarketDataProvider."
            )
        logger.info("MARKET_DATA_PROVIDER=dev -- using DevMarketDataProvider (synthetic data).")
        return DevMarketDataProvider(), "dev"

    if override not in ("auto", "sahmk"):
        logger.warning("Unknown MARKET_DATA_PROVIDER=%r -- treating as 'auto'.", override)

    if not market_data_config.has_sahmk_credentials():
        if strict:
            raise StrictRealDataUnavailableError("SAHMK_API_KEY is not configured.")
        if override == "sahmk":
            logger.error(
                "MARKET_DATA_PROVIDER=sahmk but SAHMK_API_KEY is not configured -- "
                "falling back to DevMarketDataProvider."
            )
        else:
            logger.info(
                "SAHMK_API_KEY not configured -- using DevMarketDataProvider (synthetic data)."
            )
        return DevMarketDataProvider(), "dev"

    provider = SahmkMarketDataProvider()
    try:
        reachable = await asyncio.wait_for(
            provider.authenticate(),
            timeout=market_data_config.get_provider_probe_timeout_seconds(),
        )
    except asyncio.TimeoutError:
        await provider.disconnect()
        if strict:
            raise StrictRealDataUnavailableError("SAHMK connectivity probe timed out.")
        logger.warning(
            "SAHMK connectivity probe timed out -- falling back to DevMarketDataProvider "
            "(synthetic data) for this process. This is expected in network-restricted "
            "environments; SAHMK is used automatically once network access is available."
        )
        return DevMarketDataProvider(), "dev"
    except (SahmkError, CircuitBreakerOpenError) as exc:
        await provider.disconnect()
        if strict:
            raise StrictRealDataUnavailableError(f"SAHMK connectivity probe failed: {exc}")
        logger.warning(
            "SAHMK connectivity probe failed (%s) -- falling back to DevMarketDataProvider.",
            exc,
        )
        return DevMarketDataProvider(), "dev"

    if not reachable:
        await provider.disconnect()
        if strict:
            raise StrictRealDataUnavailableError("SAHMK authentication check did not succeed.")
        logger.warning(
            "SAHMK authentication check did not succeed -- falling back to "
            "DevMarketDataProvider (synthetic data)."
        )
        return DevMarketDataProvider(), "dev"

    logger.info(
        "SAHMK is reachable and the configured API key was accepted -- "
        "using SahmkMarketDataProvider (live data)."
    )
    return provider, "sahmk"


def reset_provider_cache() -> None:
    """Test-only: clears the cached provider selection."""
    global _cached_provider, _cached_provider_kind, _cached_at
    global _last_connectivity_status, _last_connectivity_at, _last_real_data_at
    _cached_provider = None
    _cached_provider_kind = None
    _cached_at = 0.0
    _last_connectivity_status = None
    _last_connectivity_at = None
    _last_real_data_at = None
