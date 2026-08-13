"""Redis-backed leader lease so only ONE of Gunicorn's worker processes
actually drives `IntervalMarketIntelligenceScheduler`'s scan loop at a
time, even though `main.py`'s `@app.on_event("startup")` runs
independently in every worker (Dockerfile: `gunicorn ... --workers 4`)
and so calls `LiveMarketModeScheduler.start()` -> this scheduler's own
`start()` in all four.

2026-08-13 production incident: with no such lease, all four workers
ran the full scan loop concurrently and redundantly against the exact
same symbol universe, quadrupling real SAHMK request volume for
identical work and exhausting the account's daily quota within about
an hour of Tadawul's open. This module closes that gap without any
new infrastructure (no message queue, no external coordinator) --
plain Redis SETNX-with-TTL, the same lazy-shared-singleton pattern
`src.market_data.sahmk.rate_limiter`/`redis_shared_cache` already use.

Fails CLOSED, not open: if Redis is unreachable, `try_acquire_or_renew`
returns False (not-leader) rather than assuming leadership -- a worker
that can't prove it holds the lease must not scan. Silently reverting
to "every worker scans" on a Redis blip would reintroduce the exact
incident this module exists to prevent; a few minutes of paused
scanning during a real Redis outage is the smaller, disclosed harm.
"""

import logging
import uuid
from typing import Optional

import redis as redis_lib

from src.core.config import settings

logger = logging.getLogger(__name__)

_LEASE_KEY = "basirah:scheduler:market_intelligence:leader"

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
                "SchedulerLeaderLock: could not construct a Redis client (%s) -- this worker will "
                "never claim scan-loop leadership until Redis is reachable.",
                exc,
            )
            _shared_redis_client = None
    return _shared_redis_client


def reset_shared_redis_client() -> None:
    """Test-only: clears the singleton so the next call rebuilds it."""
    global _shared_redis_client, _shared_redis_client_attempted
    _shared_redis_client = None
    _shared_redis_client_attempted = False


class SchedulerLeaderLock:
    """One instance per `IntervalMarketIntelligenceScheduler`, one
    random `token` per process -- `try_acquire_or_renew()` is meant to
    be called once per loop tick, before doing any scan work."""

    def __init__(self, redis_client: "Optional[redis_lib.Redis]" = None, lease_key: str = _LEASE_KEY):
        self._redis_override = redis_client
        self._lease_key = lease_key
        self.token = uuid.uuid4().hex

    def _redis(self) -> "Optional[redis_lib.Redis]":
        return self._redis_override if self._redis_override is not None else _get_shared_redis_client()

    def try_acquire_or_renew(self, lease_seconds: float) -> bool:
        """True if this process holds (or just won) the lease for the
        next `lease_seconds`. A worker that already holds it renews the
        TTL; a worker that doesn't tries to claim it (only succeeds if
        no one else currently holds it, i.e. the previous holder's
        lease expired -- covers the previous leader crashing without
        releasing it)."""
        client = self._redis()
        if client is None:
            return False
        ttl_ms = max(1, int(lease_seconds * 1000))
        try:
            current = client.get(self._lease_key)
            if current == self.token:
                client.pexpire(self._lease_key, ttl_ms)
                return True
            won = client.set(self._lease_key, self.token, nx=True, px=ttl_ms)
            return bool(won)
        except Exception:
            logger.warning("SchedulerLeaderLock: Redis error acquiring/renewing lease.", exc_info=True)
            return False

    def release(self) -> None:
        """Best-effort early release (e.g. on graceful shutdown) so the
        next leader doesn't have to wait out the full lease TTL --
        never required for correctness (an expired, unreleased lease
        still fails over on its own), only for a faster handover."""
        client = self._redis()
        if client is None:
            return
        try:
            if client.get(self._lease_key) == self.token:
                client.delete(self._lease_key)
        except Exception:
            logger.debug("SchedulerLeaderLock: Redis error releasing lease (harmless -- it will expire).", exc_info=True)
