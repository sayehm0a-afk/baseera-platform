"""Atomic Redis-backed execution lock for the `historical_ohlcv`
ingestion job specifically (PR #108 P0 concurrency remediation).

Independent concurrency testing reproduced two near-simultaneous
manual invocations of POST .../historical-ohlcv/run-once both being
accepted, and two separate `historical_ohlcv` executions actually
running concurrently -- the route's own in-flight check (a plain
`SELECT ... WHERE finished_at IS NULL`) is not atomic: nothing reserves
a slot at check time, so two requests can both observe "nothing
running" before either one's background task has committed its own
RUNNING row. Separately, the recurring `IngestionScheduler`'s own
`historical_ohlcv` tick (`_loop`) never consulted that same check at
all, so a natural scheduled run and a manual controlled run had no
shared exclusion boundary whatsoever.

This module is distinct from `src.market_intelligence.
scheduler_leader_lock.SchedulerLeaderLock`, which answers a different
question ("which one Gunicorn worker process currently leads the
recurring ingestion scheduler") and is held for a worker's entire
lifetime. `HistoricalOhlcvExecutionLock` answers "is a historical_ohlcv
execution currently in progress, from ANY entry point" and is held
only for the duration of one such execution -- acquired fresh by
whichever caller (the manual admin route, the recurring scheduler
tick, or /full-discovery's run_all_jobs_once) gets there first.

Reuses the exact same lazy-shared-Redis-client singleton
`scheduler_leader_lock.py` already established (one client per
process, constructed on first use) and the identical atomic
`SET key value NX PX ttl_ms` acquire primitive that lock's own
`try_acquire_or_renew()` uses. Unlike that lock's own `release()`
(a plain GET-then-DELETE -- two round trips, documented there as
"best-effort... never required for correctness" because a leadership
lease's real safety net is its TTL), this lock's `release()` uses a
single atomic Lua check-and-delete: this lock's entire purpose is
duplicate-EXECUTION prevention, so an ownership-unsafe release here
would undermine the one guarantee the lock exists to provide, not
merely delay a handover.

Fails CLOSED, matching every other Redis-backed coordination primitive
in this codebase (SchedulerLeaderLock, SahmkRateLimiter): if Redis is
unreachable, `acquire()` returns False (lock not held) rather than
assuming it is safe to proceed -- a historical_ohlcv attempt that
cannot prove exclusivity must not run, not run unprotected.
"""

import logging
import uuid
from typing import Optional

from src.market_intelligence.scheduler_leader_lock import _get_shared_redis_client

logger = logging.getLogger(__name__)

HISTORICAL_OHLCV_EXECUTION_LOCK_KEY = "basirah:ingestion:historical_ohlcv:execution_lock"

# Atomic check-and-delete in one Redis round trip: only removes the key
# if its current value still matches the caller's own token. Without
# this, a plain GET-then-DELETE could delete a *different* owner's
# lock if this token's own TTL happened to expire in the gap between
# the two commands and a new owner acquired it in that same gap.
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class HistoricalOhlcvExecutionLock:
    """One instance per acquire attempt (NOT held across a process's
    lifetime the way SchedulerLeaderLock is -- a fresh instance, and a
    fresh random token, every time something wants to run
    historical_ohlcv). `acquire()` is a single atomic `SET NX PX`;
    `release()` is a single atomic Lua check-and-delete."""

    def __init__(
        self,
        redis_client: "Optional[object]" = None,
        lock_key: str = HISTORICAL_OHLCV_EXECUTION_LOCK_KEY,
    ) -> None:
        self._redis_override = redis_client
        self._lock_key = lock_key
        self.token = uuid.uuid4().hex

    def _redis(self):
        return self._redis_override if self._redis_override is not None else _get_shared_redis_client()

    def acquire(self, ttl_seconds: float) -> bool:
        """True if this call just won the lock. False if another
        owner already holds it, or Redis is unreachable -- never
        assumes success on error (fail-closed)."""
        client = self._redis()
        if client is None:
            logger.warning("HistoricalOhlcvExecutionLock: no Redis client available -- treating as not acquired.")
            return False
        ttl_ms = max(1, int(ttl_seconds * 1000))
        try:
            won = client.set(self._lock_key, self.token, nx=True, px=ttl_ms)
            return bool(won)
        except Exception:
            logger.warning("HistoricalOhlcvExecutionLock: Redis error acquiring lock.", exc_info=True)
            return False

    def release(self) -> None:
        """Atomic ownership-checked release -- a no-op (not an error)
        if the lock already expired or was never held by this
        instance's own token."""
        client = self._redis()
        if client is None:
            return
        try:
            client.eval(_RELEASE_SCRIPT, 1, self._lock_key, self.token)
        except Exception:
            logger.debug(
                "HistoricalOhlcvExecutionLock: Redis error releasing lock (harmless -- it will expire).",
                exc_info=True,
            )
