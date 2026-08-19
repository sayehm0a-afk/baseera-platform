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
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

import redis as redis_lib

from src.core.config import settings
from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data import config as market_data_config
from src.market_data.provider_connectivity_retry import (
    ProviderProbeTimeoutError,
    probe_connectivity_with_retry,
)
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkError
from src.market_data.sahmk.rate_limiter import SahmkRateLimitExceededError
from src.market_data.strict_mode import StrictRealDataUnavailableError

logger = logging.getLogger(__name__)

# 2026-08-19 production evidence: GET /api/v1/admin/system/summary reported
# market_data_health="unhealthy"/market_data_status="UNAVAILABLE" *during*
# a market-open cycle that had just successfully scanned 15/15 symbols via
# real SAHMK calls (confirmed via the SAHMK quota ledger). Root cause: the
# module-level state below (_cached_provider_kind, _last_connectivity_*)
# is explicitly process-local (see get_market_data_health()'s own
# docstring) and is only ever written by whichever Gunicorn worker actually
# ran the leader-locked scan cycle -- the other three workers' copies stay
# at their process-start defaults (None) forever unless something in that
# specific worker also happens to call get_market_data_provider(). Since
# the admin dashboard request can land on any of the four workers, the
# reported health reflected "did this specific, possibly-uninvolved worker
# ever select a provider," not "is SAHMK actually reachable." This mirrors
# the exact class of bug already fixed for the SAHMK quota ledger (see
# SahmkRateLimiter's `quota_shared_across_workers`) -- the fix here is the
# same shape: best-effort mirror the selection outcome into Redis so every
# worker can report the fleet's real, current state, while still degrading
# gracefully to this process's own local state if Redis is unavailable
# (never raises, never blocks a real caller on Redis reachability).
_SHARED_HEALTH_REDIS_KEY = "basirah:market_data_provider:shared_health"
_SHARED_HEALTH_TTL_SECONDS = 900  # several multiples of the 60s Live Market
# Mode poll interval, so a fleet that genuinely stops selecting a provider
# (e.g. market closed, all workers idle) ages back out to "no shared state
# known" instead of showing a permanently stale snapshot from hours ago.

_shared_redis_client: "Optional[redis_lib.Redis]" = None
_shared_redis_client_attempted = False


def _get_shared_redis_client() -> "Optional[redis_lib.Redis]":
    """Lazily constructs a Redis client from settings.redis_dsn once per
    process, or returns None if that isn't possible -- same best-effort,
    per-module pattern as SahmkRateLimiter._get_shared_redis_client() and
    SchedulerLeaderLock's own client accessor. A missing/unreachable Redis
    only means this module falls back to process-local state (its
    pre-existing, still-fully-functional behavior), never an error."""
    global _shared_redis_client, _shared_redis_client_attempted
    if not _shared_redis_client_attempted:
        _shared_redis_client_attempted = True
        try:
            _shared_redis_client = redis_lib.Redis.from_url(
                settings.redis_dsn, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
            )
        except Exception as exc:
            logger.warning(
                "provider_factory: could not construct a Redis client (%s) -- market-data "
                "provider health will only be tracked in this process's own memory, not "
                "shared across workers.",
                exc,
            )
            _shared_redis_client = None
    return _shared_redis_client


def _write_shared_health_snapshot(
    provider_kind: Optional[str],
    connectivity_status: Optional[str],
    connectivity_at: datetime,
    real_data_at: Optional[datetime],
) -> None:
    """Best-effort mirror of this process's own just-observed selection
    outcome into Redis, so any worker answering an admin/health request
    can report it -- never raises, never blocks a real caller on this."""
    client = _get_shared_redis_client()
    if client is None:
        return
    try:
        payload = json.dumps(
            {
                "current_provider_kind": provider_kind,
                "last_connectivity_status": connectivity_status,
                "last_connectivity_at": connectivity_at.isoformat(),
                "last_real_data_at": real_data_at.isoformat() if real_data_at else None,
            }
        )
        client.set(_SHARED_HEALTH_REDIS_KEY, payload, ex=_SHARED_HEALTH_TTL_SECONDS)
    except Exception:
        logger.warning("provider_factory: failed to write shared market-data health snapshot.", exc_info=True)


def _read_shared_health_snapshot() -> Optional[dict]:
    """Best-effort read of the fleet-wide snapshot; None if Redis is
    unavailable, the key hasn't been written/has expired, or the stored
    value is malformed -- every case degrading to the caller's own
    process-local state, never raising."""
    client = _get_shared_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(_SHARED_HEALTH_REDIS_KEY)
        return json.loads(raw) if raw else None
    except Exception:
        logger.warning("provider_factory: failed to read shared market-data health snapshot.", exc_info=True)
        return None


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
    """Secret-free snapshot for GET /health/market-data and the admin
    dashboard. Never touches the network itself -- reports the outcome
    of whatever the most recent real selection attempt (by any caller,
    in any Gunicorn worker) already found.

    Prefers the shared (Redis-backed) snapshot over this process's own
    local state whenever the shared one is present and at least as
    recent: with multiple worker processes, only whichever worker
    actually ran the leader-locked scan cycle has fresh *local* state,
    so a caller landing on a different worker would otherwise see stale
    process-start defaults even while the fleet is genuinely healthy
    (2026-08-19 production evidence -- see this module's own top-level
    comment). Falls back to local state whenever Redis is unavailable
    or the shared snapshot is missing/older, so behavior in
    Redis-less environments (tests, CI) is unchanged."""
    current_provider_kind = _cached_provider_kind
    last_connectivity_status = _last_connectivity_status
    last_connectivity_at = _last_connectivity_at
    last_real_data_at = _last_real_data_at

    shared = _read_shared_health_snapshot()
    if shared is not None:
        shared_at = _parse_iso(shared.get("last_connectivity_at"))
        if shared_at is not None and (last_connectivity_at is None or shared_at >= last_connectivity_at):
            current_provider_kind = shared.get("current_provider_kind")
            last_connectivity_status = shared.get("last_connectivity_status")
            last_connectivity_at = shared_at
            last_real_data_at = _parse_iso(shared.get("last_real_data_at"))

    return {
        "configured_provider": market_data_config.get_configured_provider_name(),
        "strict_real_data": market_data_config.is_strict_real_data_enabled(),
        "synthetic_allowed": market_data_config.is_synthetic_data_allowed(),
        "sahmk_key_present": market_data_config.has_sahmk_credentials(),
        "current_provider_kind": current_provider_kind,
        "last_connectivity_status": last_connectivity_status,
        "last_connectivity_at": last_connectivity_at.isoformat() if last_connectivity_at else None,
        "last_real_data_at": last_real_data_at.isoformat() if last_real_data_at else None,
    }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


async def get_market_data_provider(force_refresh: bool = False) -> IMarketDataProvider:
    """Returns the IMarketDataProvider the caller should use right now.

    A cache refresh (expiry or force_refresh=True) re-verifies
    reachability with a real network call every time, but does NOT
    unconditionally throw away and reconnect the underlying
    SahmkMarketDataProvider: _select_provider() reuses the previous
    instance (and its live aiohttp session) whenever it's still the
    right kind, so the common steady-state case (SAHMK healthy, cache
    just expiring on schedule) never swaps the session out at all. See
    _select_provider()'s docstring for why this matters -- it closes a
    real concurrency bug, not just an inefficiency.

    Only a genuine kind change (sahmk -> dev fallback, or vice versa)
    still supersedes the cached provider. That provider is disconnected
    via _disconnect_with_grace() rather than an immediate close, for
    the same reason: something else may still be mid-request against
    it.
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
            provider, kind = await _select_provider(previous_provider)
        except StrictRealDataUnavailableError:
            _last_connectivity_status = "FAILED"
            _last_connectivity_at = datetime.now(timezone.utc)
            # A real, surfaced failure (re-raised below) -- still mirrored
            # to the shared snapshot so every worker's dashboard reflects
            # it too, not just the worker that happened to hit it.
            _write_shared_health_snapshot(
                _cached_provider_kind, _last_connectivity_status, _last_connectivity_at, _last_real_data_at
            )
            raise

        _last_connectivity_status = "SUCCESS" if kind == "sahmk" else "FAILED"
        _last_connectivity_at = datetime.now(timezone.utc)
        if kind == "sahmk":
            _last_real_data_at = _last_connectivity_at

        _write_shared_health_snapshot(kind, _last_connectivity_status, _last_connectivity_at, _last_real_data_at)

        if previous_provider is not None and previous_provider is not provider:
            _disconnect_with_grace(previous_provider)

        _cached_provider = provider
        _cached_provider_kind = kind
        _cached_at = now
        return provider


_pending_disconnects: "set[asyncio.Task]" = set()


def _disconnect_with_grace(provider: IMarketDataProvider) -> None:
    """Schedules a superseded provider's disconnect after a grace
    delay instead of closing it immediately.

    Root cause this replaces: get_market_data_provider() used to call
    provider.disconnect() synchronously, right inside _cache_lock, the
    instant a refresh superseded it. A live SahmkMarketDataProvider's
    disconnect() closes its single shared aiohttp ClientSession
    (src.market_data.sahmk.client.SahmkClient._session). Any caller
    that had already fetched that *same* provider instance moments
    earlier and was still using it -- most notably
    ingest_historical_ohlcv's per-symbol loop, which the SAHMK rate
    limiter routinely stalls for up to ~60s between requests, easily
    outliving the default 60s cache window -- would have its in-flight
    or next `session.get()` call fail with aiohttp's internal
    `AssertionError: assert self._connector is not None`, surfaced as
    "Circuit breaker operation failed in CLOSED state" in production
    logs (confirmed via two independent production audit runs).

    _select_provider() reusing the same instance across refreshes when
    its kind is unchanged already eliminates this in the common case
    (SAHMK staying healthy). This function covers the residual case --
    a genuine kind change -- by giving any straggling concurrent caller
    a real chance to finish before the session is torn down, instead of
    closing it out from under them. The task reference is kept in
    _pending_disconnects so it isn't garbage-collected mid-flight and
    is removed again once it completes.
    """

    async def _delayed_disconnect() -> None:
        try:
            await asyncio.sleep(market_data_config.get_provider_disconnect_grace_seconds())
            await provider.disconnect()
        except Exception:
            logger.warning("Error disconnecting a superseded market data provider.", exc_info=True)

    task = asyncio.ensure_future(_delayed_disconnect())
    _pending_disconnects.add(task)
    task.add_done_callback(_pending_disconnects.discard)


def get_last_selected_provider_kind() -> Optional[str]:
    """"dev" | "sahmk" | None (nothing selected yet) -- for diagnostics
    (e.g. a status endpoint) without exposing any credential."""
    return _cached_provider_kind


def get_cached_provider_circuit_breaker_state() -> Optional[str]:
    """"CLOSED" | "OPEN" | "HALF_OPEN" | None -- reads the *currently
    cached* provider's own SahmkClient circuit breaker state, purely
    from memory (no network call, no cache refresh). None when nothing
    is cached yet or the cached provider isn't a SahmkMarketDataProvider
    (e.g. DevMarketDataProvider, which has no breaker at all).

    Deliberately defensive (getattr chains, never raises): this is a
    diagnostics-only accessor reaching into another module's internals
    across three layers (provider -> service -> client -> breaker) --
    any of them being reshaped later should degrade this to None, not
    break the admin dashboard.
    """
    client = getattr(getattr(_cached_provider, "_service", None), "_client", None)
    breaker = getattr(client, "_circuit_breaker", None)
    state = getattr(breaker, "state", None)
    return state.value if state is not None else None


async def _select_provider(
    previous_provider: Optional[IMarketDataProvider] = None,
) -> Tuple[IMarketDataProvider, str]:
    """Chooses the provider for this refresh, re-verifying reachability
    with a real network call every time -- but reuses `previous_provider`
    (and its live aiohttp session) instead of constructing a fresh
    SahmkMarketDataProvider whenever it's already the right kind.

    This is the actual fix for the aiohttp ClientSession concurrency
    bug this module used to only disclose: without reuse, every single
    cache refresh (default every 60s) built a brand-new
    SahmkMarketDataProvider and closed the outgoing one, even when
    SAHMK was perfectly healthy both before and after. A caller that
    had fetched the outgoing provider moments earlier and was still
    using it -- in production, almost always the ingestion scheduler's
    per-symbol loop, which the SAHMK rate limiter routinely stalls for
    up to ~60s between requests -- could have its session closed out
    from under it mid-loop, surfacing as aiohttp's internal
    `AssertionError: assert self._connector is not None`. Reusing the
    same instance across refreshes means the steady-state case (SAHMK
    staying healthy) never swaps or closes a session at all.
    SahmkMarketDataProvider.authenticate() is a real, idempotent
    network probe -- safe to call repeatedly on the same instance, and
    still gives force_refresh callers a genuinely fresh reachability
    check, just without discarding a perfectly good connection.
    """
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

    reused = isinstance(previous_provider, SahmkMarketDataProvider)
    provider = previous_provider if reused else SahmkMarketDataProvider()

    # A reused instance's own session must never be closed here on
    # failure -- get_market_data_provider() already handles that via
    # _disconnect_with_grace() once it sees the kind has changed. Only
    # a brand-new, not-yet-cached instance is safe to close immediately
    # (nothing else can be holding a reference to it yet).
    async def _cleanup_on_failure() -> None:
        if not reused:
            await provider.disconnect()

    try:
        reachable = await probe_connectivity_with_retry(
            provider.check_connectivity, provider_label="SahmkMarketDataProvider"
        )
    except ProviderProbeTimeoutError:
        await _cleanup_on_failure()
        if strict:
            raise StrictRealDataUnavailableError("SAHMK connectivity probe timed out after retrying.")
        logger.warning(
            "SAHMK connectivity probe timed out after retrying -- falling back to "
            "DevMarketDataProvider (synthetic data) for this process. This is expected in "
            "network-restricted environments; SAHMK is used automatically once network "
            "access is available."
        )
        return DevMarketDataProvider(), "dev"
    except (SahmkError, SahmkRateLimitExceededError, CircuitBreakerOpenError) as exc:
        await _cleanup_on_failure()
        if strict:
            raise StrictRealDataUnavailableError(f"SAHMK connectivity probe failed: {exc}")
        logger.warning(
            "SAHMK connectivity probe failed (%s) -- falling back to DevMarketDataProvider.",
            exc,
        )
        return DevMarketDataProvider(), "dev"

    if not reachable:
        await _cleanup_on_failure()
        if strict:
            raise StrictRealDataUnavailableError("SAHMK authentication check did not succeed.")
        logger.warning(
            "SAHMK authentication check did not succeed -- falling back to "
            "DevMarketDataProvider (synthetic data)."
        )
        return DevMarketDataProvider(), "dev"

    logger.info(
        "SAHMK is reachable and the configured API key was accepted -- using "
        "%s SahmkMarketDataProvider (live data).",
        "the existing" if reused else "a new",
    )
    return provider, "sahmk"


def reset_provider_cache() -> None:
    """Test-only: clears the cached provider selection (local and, if a
    real Redis happens to be reachable, the shared snapshot too -- best
    effort, never raises)."""
    global _cached_provider, _cached_provider_kind, _cached_at
    global _last_connectivity_status, _last_connectivity_at, _last_real_data_at
    _cached_provider = None
    _cached_provider_kind = None
    _cached_at = 0.0
    _last_connectivity_status = None
    _last_connectivity_at = None
    _last_real_data_at = None
    client = _get_shared_redis_client()
    if client is not None:
        try:
            client.delete(_SHARED_HEALTH_REDIS_KEY)
        except Exception:
            pass
