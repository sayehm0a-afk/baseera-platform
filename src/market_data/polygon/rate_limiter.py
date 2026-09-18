"""Process-wide rate limiter for Polygon.io API calls.

Polygon's quota is per API key, account-wide -- a limiter owned by each
PolygonClient instance individually would let independent clients draw
independent budgets, doubling real usage against the one account limit
both actually share. This module's `get_default_polygon_rate_limiter()`
is a lazily-constructed singleton every PolygonClient uses by default,
mirroring src.market_data.sahmk.rate_limiter's `get_default_rate_limiter()`
pattern -- consistent with the `rate_limiter=` override pattern
PolygonClient already has, so tests can still inject their own instance
instead of sharing the real singleton.

v1 is deliberately scoped to a per-minute sliding window only -- no
daily quota, no priority-tiered reserves, no cross-process Redis
sharing. Polygon.io's Free tier (the only tier this integration targets
so far; its real, documented limit is 5 requests/minute, with no
separate daily cap) has nothing for those mechanisms to protect yet.
Should a future task add a paid tier with its own daily/burst
structure, that would extend this class the same way SahmkRateLimiter
was incrementally extended -- not something to guess at pre-emptively
here.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Deque, Dict, Optional

from src.market_data import config as market_data_config

logger = logging.getLogger(__name__)


class PolygonRateLimiter:
    """Sliding-window limiter: at most `max_per_minute` acquire() calls
    complete in any trailing 60s window. Mirrors SahmkRateLimiter's own
    sliding-window mechanism (src.market_data.sahmk.rate_limiter)
    exactly, minus the daily-quota/priority-reserve/Redis-sharing
    machinery that limiter also has -- see this module's docstring for
    why v1 doesn't need any of that yet.
    """

    def __init__(self, max_per_minute: int):
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        self._max_per_minute = max_per_minute
        self._minute_window: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Blocks (sleeping, never busy-waiting) until a slot is free
        under the per-minute window, then reserves it."""
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._minute_window and now - self._minute_window[0] >= 60.0:
                    self._minute_window.popleft()
                if len(self._minute_window) < self._max_per_minute:
                    break
                wait_seconds = 60.0 - (now - self._minute_window[0])
                logger.info(
                    "Polygon rate limiter: %d/%d requests used in the last minute -- waiting %.2fs.",
                    len(self._minute_window),
                    self._max_per_minute,
                    wait_seconds,
                )
                await asyncio.sleep(max(wait_seconds, 0.01))

            self._minute_window.append(time.monotonic())

    def get_status(self) -> Dict[str, object]:
        """Secret-free snapshot for admin/system-health diagnostics --
        never touches the network."""
        now = time.monotonic()
        while self._minute_window and now - self._minute_window[0] >= 60.0:
            self._minute_window.popleft()
        return {
            "max_per_minute": self._max_per_minute,
            "requests_in_last_minute": len(self._minute_window),
        }

    def reset(self) -> None:
        """Test-only: clears all tracked usage."""
        self._minute_window.clear()


_default_rate_limiter: Optional[PolygonRateLimiter] = None


def get_default_polygon_rate_limiter() -> PolygonRateLimiter:
    """Returns the process-wide PolygonRateLimiter, constructing it from
    src.market_data.config on first use. Every PolygonClient shares this
    same instance unless a caller explicitly passes its own."""
    global _default_rate_limiter
    if _default_rate_limiter is None:
        _default_rate_limiter = PolygonRateLimiter(
            max_per_minute=market_data_config.get_polygon_max_requests_per_minute()
        )
    return _default_rate_limiter


def reset_default_polygon_rate_limiter() -> None:
    """Test-only: clears the singleton so the next
    get_default_polygon_rate_limiter() call rebuilds it from the current
    environment/config."""
    global _default_rate_limiter
    _default_rate_limiter = None
