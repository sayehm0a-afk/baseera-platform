"""In-memory, per-process TTL cache for market-data provider responses.

======================================================================
ARCHITECTURAL DECISION: in-memory, not Redis-backed
======================================================================
Same reasoning already established for src.api.middleware.rate_limit
(M2.12): `src.core.messaging.redis_message_bus` exists and could back a
shared cache, but Redis is not reliably available in every environment
this app runs in (confirmed repeatedly across this project's own
milestones -- `redis-cli ping` fails in this sandbox). A per-process
cache is correct and self-contained for a single instance; a
horizontally-scaled deployment would need a shared backend, a known,
disclosed limitation, not something silently pretended away. Swapping
the storage backend later is contained to this one class -- callers
use `get_or_compute`, never the storage directly.
"""

import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

_MISSING = object()


class TTLCache:
    def __init__(self, default_ttl_seconds: float = 60.0) -> None:
        self._default_ttl = default_ttl_seconds
        self._store: Dict[Any, Tuple[float, Any]] = {}

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
    ) -> Any:
        """The main integration point: returns the cached value if
        present and unexpired, otherwise awaits `compute()`, caches the
        result, and returns it. `compute` is only ever called on a
        cache miss -- never speculatively."""
        cached = self.get(key)
        if cached is not _MISSING:
            return cached
        value = await compute()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value
