"""Process-shared TTL cache for market-data provider responses, backed
by Redis so all Gunicorn workers reuse the same cached result instead
of each worker's own in-memory `TTLCache` (see ttl_cache.py) drawing an
independent SAHMK request for the same symbol/window.

Same lazy-shared-singleton-with-test-override pattern as
src.market_data.sahmk.rate_limiter's `_get_shared_redis_client()` --
constructing the client never connects eagerly, so a genuinely
unreachable Redis is discovered per-call, not at import time, and every
Redis-touching branch below degrades to `TTLCache`'s existing
in-process behavior (the same one already relied on when no Redis is
configured at all) rather than raising -- a Redis outage must never
crash Basirah.

Stampede prevention: when multiple workers miss the cache for the same
key at once, only the first to win a short-lived `SET key:lock NX`
actually calls the provider; the rest poll the (much cheaper) cache key
briefly and reuse whatever the winner writes. If the winner's process
dies before writing (crash, OOM-kill) the lock simply expires and a
later poller computes it directly -- never a permanent deadlock.

Serialization: every value cached through this module is a frozen,
flat dataclass (see src.market_data.sahmk.models) or a list of them --
`_encode_value`/`_decode_value` use `dataclasses.fields()` to convert
`datetime` fields to/from ISO-8601 strings and pass every other field
through JSON natively, so no per-model boilerplate is needed here or at
any call site.
"""

import asyncio
import dataclasses
import json
import logging
import typing
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Type, TypeVar

import redis as redis_lib

from src.core.config import settings
from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.sahmk.operation_scope import UNCLASSIFIED, get_current_operation

logger = logging.getLogger(__name__)

T = TypeVar("T")

_LOCK_TTL_MS = 10_000  # generous upper bound on a real SAHMK round trip
_POLL_INTERVAL_SECONDS = 0.1
_POLL_MAX_ATTEMPTS = 40  # ~4s total -- longer than any real SAHMK call is expected to take

_KEY_PREFIX = "basirah:mdcache:"


def _stable_key(key: Any) -> str:
    """Deterministic string form of a cache key -- call sites already
    pass tuples of primitives (see service.py), so `str()` on the tuple
    is already stable and human-readable in Redis (e.g. `('quote',
    '2222')`); this exists as one seam in case a future key shape ever
    needs different handling."""
    return str(key)


def _encode_value(value: Any) -> Any:
    """dataclass/list-of-dataclass -> JSON-safe. `datetime`/`date`
    fields become ISO strings; every other field (str/int/float/bool/
    None/dict/list) already round-trips through json.dumps unchanged."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: Dict[str, Any] = {}
        for f in dataclasses.fields(value):
            v = getattr(value, f.name)
            out[f.name] = v.isoformat() if isinstance(v, (datetime, date)) else v
        return out
    if isinstance(value, list):
        return [_encode_value(item) for item in value]
    return value


def _is_datetime_annotation(field_type: Any) -> bool:
    """True for a bare `datetime` annotation or `Optional[datetime]`
    (== `Union[datetime, None]`) -- the only two shapes any field in
    src.market_data.sahmk.models actually uses for a timestamp."""
    if field_type is datetime:
        return True
    return datetime in typing.get_args(field_type)


def _decode_value(payload: Any, cls: Optional[Type[T]]) -> Any:
    """Inverse of `_encode_value`. `cls=None` returns the JSON-safe
    payload unchanged (used for values that were never dataclasses to
    begin with)."""
    if cls is None:
        return payload
    if isinstance(payload, list):
        return [_decode_value(item, cls) for item in payload]
    kwargs = {}
    for f in dataclasses.fields(cls):
        raw = payload.get(f.name)
        if raw is not None and _is_datetime_annotation(f.type):
            kwargs[f.name] = datetime.fromisoformat(raw)
        else:
            kwargs[f.name] = raw
    return cls(**kwargs)


class CacheBackendHealth:
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Redis configured but unreachable right now
    DISABLED = "disabled"  # no Redis configured at all


@dataclasses.dataclass
class SharedCacheStats:
    """Secret-free counters for admin/system-summary observability --
    never touches the network itself; only ever incremented by the
    cache operations below."""

    hits: int = 0
    misses: int = 0
    coalesced_waits: int = 0
    provider_calls: int = 0
    redis_errors: int = 0

    def as_dict(self) -> Dict[str, int]:
        return dataclasses.asdict(self)


_shared_redis_client: "Optional[redis_lib.Redis]" = None
_shared_redis_client_attempted = False


def _get_shared_redis_client() -> "Optional[redis_lib.Redis]":
    global _shared_redis_client, _shared_redis_client_attempted
    if not _shared_redis_client_attempted:
        _shared_redis_client_attempted = True
        try:
            _shared_redis_client = redis_lib.Redis.from_url(
                settings.redis_dsn, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
            )
        except Exception as exc:
            logger.warning(
                "SharedTTLCache: could not construct a Redis client (%s) -- market-data caching "
                "will only be shared within this one worker process, not across all of them.",
                exc,
            )
            _shared_redis_client = None
    return _shared_redis_client


def reset_shared_redis_client() -> None:
    """Test-only: clears the singleton so the next call rebuilds it."""
    global _shared_redis_client, _shared_redis_client_attempted
    _shared_redis_client = None
    _shared_redis_client_attempted = False


class SharedTTLCache:
    """Drop-in replacement for `TTLCache.get_or_compute()` -- same
    signature plus an optional `model` (the dataclass type to decode
    cache hits back into; `None` for already-JSON-safe values) -- that
    additionally shares results across every Gunicorn worker via Redis,
    with `TTLCache`'s existing per-process behavior as the fallback
    whenever Redis is unavailable for any reason."""

    def __init__(self, namespace: str, redis_client: "Optional[redis_lib.Redis]" = None):
        self._namespace = namespace
        self._redis_override = redis_client
        self._local = TTLCache()
        self.stats = SharedCacheStats()
        self.stats_by_operation: Dict[str, SharedCacheStats] = {}

    def _redis(self) -> "Optional[redis_lib.Redis]":
        return self._redis_override if self._redis_override is not None else _get_shared_redis_client()

    def _record(self, field: str, operation_key: str) -> None:
        """Increments `field` on both the flat totals (`self.stats`,
        unchanged behavior) and the per-operation breakdown
        (`self.stats_by_operation[operation_key]`, new) -- the audit
        mandate's "cache_hits, cache_misses, coalesced_requests,
        duplicate_requests_prevented ... by operation" requirement.
        `coalesced_waits` doubles as "duplicate_requests_prevented":
        every coalesced wait is, by construction, one caller that did
        NOT trigger its own extra provider call because another
        in-flight request already covered it."""
        setattr(self.stats, field, getattr(self.stats, field) + 1)
        bucket = self.stats_by_operation.setdefault(operation_key, SharedCacheStats())
        setattr(bucket, field, getattr(bucket, field) + 1)

    @staticmethod
    def _operation_key(key: Any) -> str:
        """Compound "subsystem:endpoint" key, mirroring
        sahmk.rate_limiter's own _operation_key: `endpoint` is the cache
        key's own leading element (call sites already pass tuples like
        `("quote", symbol)` -- see _stable_key's docstring above --
        which is already the SAHMK-data-type category), `subsystem`
        comes from the same operation_scope contextvar client.py reads
        for the rate limiter's half of this same accounting."""
        endpoint = key[0] if isinstance(key, tuple) and key else (key if isinstance(key, str) else "other")
        subsystem = get_current_operation() or UNCLASSIFIED
        return f"{subsystem}:{endpoint}"

    @property
    def backend_health(self) -> str:
        client = self._redis()
        if client is None:
            return CacheBackendHealth.DISABLED
        try:
            client.ping()
            return CacheBackendHealth.HEALTHY
        except Exception:
            return CacheBackendHealth.DEGRADED

    def _redis_key(self, key: Any) -> str:
        return f"{_KEY_PREFIX}{self._namespace}:{_stable_key(key)}"

    async def get_or_compute(
        self,
        key: Any,
        compute: Callable[[], Awaitable[T]],
        ttl_seconds: float,
        model: Optional[Type[T]] = None,
    ) -> T:
        operation_key = self._operation_key(key)
        client = self._redis()
        if client is None:
            return await self._local.get_or_compute(key, compute, ttl_seconds=ttl_seconds)

        redis_key = self._redis_key(key)
        try:
            raw = client.get(redis_key)
        except Exception:
            self.stats.redis_errors += 1
            return await self._local.get_or_compute(key, compute, ttl_seconds=ttl_seconds)

        if raw is not None:
            self._record("hits", operation_key)
            return _decode_value(json.loads(raw), model)

        self._record("misses", operation_key)
        return await self._compute_and_share(client, redis_key, compute, ttl_seconds, model, operation_key)

    async def _compute_and_share(
        self,
        client: "redis_lib.Redis",
        redis_key: str,
        compute: Callable[[], Awaitable[T]],
        ttl_seconds: float,
        model: Optional[Type[T]],
        operation_key: str,
    ) -> T:
        lock_key = redis_key + ":lock"
        try:
            got_lock = bool(client.set(lock_key, "1", nx=True, px=_LOCK_TTL_MS))
        except Exception:
            self.stats.redis_errors += 1
            got_lock = None  # neither confirmed winner nor confirmed loser -- treat as winner below

        if got_lock is False:
            waited = await self._wait_for_result(client, redis_key, model, operation_key)
            if waited is not _MISSING:
                return waited
            # Lock-holder never wrote a result (crashed, or its own
            # SAHMK call is still slower than our poll budget) -- fall
            # through and compute it ourselves rather than deadlock or
            # return nothing.

        self._record("provider_calls", operation_key)
        value = await compute()
        try:
            client.setex(redis_key, int(ttl_seconds), json.dumps(_encode_value(value)))
        except Exception:
            self.stats.redis_errors += 1  # the value is still returned even if sharing it failed
        if got_lock:
            try:
                client.delete(lock_key)
            except Exception:
                pass
        return value

    async def _wait_for_result(
        self, client: "redis_lib.Redis", redis_key: str, model: Optional[Type[T]], operation_key: str
    ):
        self._record("coalesced_waits", operation_key)
        for _ in range(_POLL_MAX_ATTEMPTS):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            try:
                raw = client.get(redis_key)
            except Exception:
                self.stats.redis_errors += 1
                return _MISSING
            if raw is not None:
                self._record("hits", operation_key)
                return _decode_value(json.loads(raw), model)
        return _MISSING


_MISSING = object()

_default_sahmk_cache: Optional[SharedTTLCache] = None


def get_default_sahmk_cache() -> SharedTTLCache:
    """The one shared cache both SahmkMarketDataProvider and
    SahmkFundamentalDataProvider construct their SahmkMarketDataService
    with -- a single process-wide instance (mirroring
    src.market_data.sahmk.rate_limiter's `get_default_rate_limiter()`
    singleton pattern) so every worker's own two providers, not just
    every worker against every other worker, share one cache."""
    global _default_sahmk_cache
    if _default_sahmk_cache is None:
        _default_sahmk_cache = SharedTTLCache("sahmk_market_data")
    return _default_sahmk_cache


def reset_default_sahmk_cache() -> None:
    """Test-only: clears the singleton so the next call rebuilds it."""
    global _default_sahmk_cache
    _default_sahmk_cache = None


def get_observability_snapshot(caches: Dict[str, "SharedTTLCache"]) -> Dict[str, Any]:
    """Secret-free summary for the admin system-summary endpoint --
    never touches raw Redis credentials, only aggregate counters and
    the backend health enum."""
    return {
        "backend_health": next(iter(caches.values())).backend_health if caches else CacheBackendHealth.DISABLED,
        "by_namespace": {name: cache.stats.as_dict() for name, cache in caches.items()},
        # "subsystem:endpoint" -> SharedCacheStats dict, merged across
        # every cache in `caches` (today there's one: "sahmk_market_data")
        # -- real, measured cache hit/miss/coalesced/provider-call counts
        # per Basirah subsystem and SAHMK data type, tracked from
        # deployment forward only (see operation_scope.py).
        "by_operation": {
            operation_key: bucket.as_dict()
            for cache in caches.values()
            for operation_key, bucket in cache.stats_by_operation.items()
        },
    }
