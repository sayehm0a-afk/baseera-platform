"""In-memory, per-process TTL cache for market-data provider responses.

ARCHITECTURAL DECISION: in-memory, not Redis-backed. A shared cache
would need Redis, which is not guaranteed available in every environment
this app runs in. A per-process cache is correct and self-contained for
a single instance; a horizontally-scaled deployment would need a shared
backend -- a known, disclosed limitation, not something silently
pretended away. Swapping the storage backend later is contained to this
one class, since every caller goes through get_or_compute(), never the
storage directly.

Concurrent callers requesting the same key while a compute() is already
in flight share that one call instead of each triggering their own --
meaningful once a real, metered vendor sits behind this cache.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

_MISSING = object()


class TTLCache:
    def __init__(self, default_ttl_seconds: float = 60.0) -> None:
        self._default_ttl = default_ttl_seconds
        self._store: Dict[Any, Tuple[float, Any]] = {}
        self._in_flight: Dict[Any, "asyncio.Task[Any]"] = {}

    def get(self, key: Any) -> Any:
        """Returns the cached value, or the module-level `_MISSING`
        sentinel if absent or expired -- distinct from a cached `None`,
        which is a legitimate value to store."""
        entry = self._store.get(key)
        if entry is None:
            return _MISSING
        expires_at, value = entry
        if time.time() >= expires_at:
            del self._store[key]
            return _MISSING
        return value

    def set(self, key: Any, value: Any, ttl_seconds: Optional[float] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = (time.time() + ttl, value)

    def clear(self) -> None:
        self._store.clear()

    async def get_or_compute(
        self,
        key: Any,
        compute: Callable[[], Awaitable[Any]],
        ttl_seconds: Optional[float] = None,
        model: Optional[type] = None,
    ) -> Any:
        """Returns the cached value if present and unexpired. Otherwise,
        if another caller is already computing this key, awaits that
        caller's in-flight result instead of issuing a second call;
        otherwise awaits compute() itself, caches the result, and
        returns it.

        `model` is accepted and ignored here -- it exists only so this
        class stays a drop-in match for
        src.market_data.caching.redis_shared_cache.SharedTTLCache's
        signature (which needs it to decode a Redis-stored value back
        into the right dataclass); an in-process cache stores the
        living Python object directly and never needs to decode
        anything.

        Every caller -- the one that starts the computation and any that
        join it while in flight -- awaits the same asyncio.Task, so a
        failure is always retrieved by at least one awaiter and never
        leaks the "Task exception was never retrieved" warning a
        manually-managed Future would in the single-caller case."""
        cached = self.get(key)
        if cached is not _MISSING:
            return cached

        existing_task = self._in_flight.get(key)
        if existing_task is not None:
            return await existing_task

        task: "asyncio.Task[Any]" = asyncio.ensure_future(compute())
        self._in_flight[key] = task
        try:
            value = await task
        finally:
            self._in_flight.pop(key, None)

        self.set(key, value, ttl_seconds=ttl_seconds)
        return value
