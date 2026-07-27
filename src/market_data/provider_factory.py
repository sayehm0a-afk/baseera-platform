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
from typing import Optional, Tuple

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data import config as market_data_config
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkError

logger = logging.getLogger(__name__)

_cache_lock = asyncio.Lock()
_cached_provider: Optional[IMarketDataProvider] = None
_cached_provider_kind: Optional[str] = None
_cached_at: float = 0.0


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
        provider, kind = await _select_provider()

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

    if override == "dev":
        logger.info("MARKET_DATA_PROVIDER=dev -- using DevMarketDataProvider (synthetic data).")
        return DevMarketDataProvider(), "dev"

    if override not in ("auto", "sahmk"):
        logger.warning("Unknown MARKET_DATA_PROVIDER=%r -- treating as 'auto'.", override)

    if not market_data_config.has_sahmk_credentials():
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
        logger.warning(
            "SAHMK connectivity probe timed out -- falling back to DevMarketDataProvider "
            "(synthetic data) for this process. This is expected in network-restricted "
            "environments; SAHMK is used automatically once network access is available."
        )
        await provider.disconnect()
        return DevMarketDataProvider(), "dev"
    except (SahmkError, CircuitBreakerOpenError) as exc:
        logger.warning(
            "SAHMK connectivity probe failed (%s) -- falling back to DevMarketDataProvider.",
            exc,
        )
        await provider.disconnect()
        return DevMarketDataProvider(), "dev"

    if not reachable:
        logger.warning(
            "SAHMK authentication check did not succeed -- falling back to "
            "DevMarketDataProvider (synthetic data)."
        )
        await provider.disconnect()
        return DevMarketDataProvider(), "dev"

    logger.info(
        "SAHMK is reachable and the configured API key was accepted -- "
        "using SahmkMarketDataProvider (live data)."
    )
    return provider, "sahmk"


def reset_provider_cache() -> None:
    """Test-only: clears the cached provider selection."""
    global _cached_provider, _cached_provider_kind, _cached_at
    _cached_provider = None
    _cached_provider_kind = None
    _cached_at = 0.0
