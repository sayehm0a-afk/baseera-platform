"""Process-wide rate limiter for SAHMK API calls.

SAHMK's quota is per API key -- account-wide, not per SahmkClient
instance. src.market_data.provider_factory and
fundamental_provider_factory each hold a *separate* SahmkClient
(market data vs. fundamentals), so a limiter owned by each client
individually would let the two draw independent budgets, doubling real
usage against the one account limit both actually share. This module's
`get_default_rate_limiter()` is a lazily-constructed singleton every
SahmkClient uses by default -- consistent with the `circuit_breaker=`
override pattern SahmkClient already has, so tests can still inject
their own instance instead of sharing the real singleton.
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Optional

from src.market_data import config as market_data_config

logger = logging.getLogger(__name__)


class SahmkRateLimitExceededError(Exception):
    """Raised when the configured daily quota is already spent for
    today (UTC). Fails fast rather than sleeping for up to 24h --
    callers (an ingestion job) should treat this as "stop for today,"
    not retry."""


class SahmkRateLimiter:
    """Sliding-window limiter: at most `max_per_minute` acquire() calls
    complete in any trailing 60s window. If `max_per_day` is set,
    acquire() also refuses (raising SahmkRateLimitExceededError) once
    that many calls have been made since the last UTC midnight.
    """

    def __init__(self, max_per_minute: int, max_per_day: Optional[int] = None):
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        if max_per_day is not None and max_per_day <= 0:
            raise ValueError("max_per_day must be positive if set")
        self._max_per_minute = max_per_minute
        self._max_per_day = max_per_day
        self._minute_window: Deque[float] = deque()
        self._day_key: Optional[str] = None
        self._day_count = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Blocks (sleeping, never busy-waiting) until a slot is free
        under the per-minute window, then reserves it. Raises
        immediately -- never sleeps -- if the daily quota is already
        spent."""
        async with self._lock:
            self._roll_day_window_locked()
            if self._max_per_day is not None and self._day_count >= self._max_per_day:
                raise SahmkRateLimitExceededError(
                    f"SAHMK daily request quota ({self._max_per_day}) already reached for today (UTC)."
                )

            while True:
                now = time.monotonic()
                while self._minute_window and now - self._minute_window[0] >= 60.0:
                    self._minute_window.popleft()
                if len(self._minute_window) < self._max_per_minute:
                    break
                wait_seconds = 60.0 - (now - self._minute_window[0])
                logger.info(
                    "SAHMK rate limiter: %d/%d requests used in the last minute -- waiting %.2fs.",
                    len(self._minute_window),
                    self._max_per_minute,
                    wait_seconds,
                )
                await asyncio.sleep(max(wait_seconds, 0.01))

            self._minute_window.append(time.monotonic())
            self._day_count += 1

    def _roll_day_window_locked(self) -> None:
        today_key = datetime.now(timezone.utc).date().isoformat()
        if today_key != self._day_key:
            self._day_key = today_key
            self._day_count = 0

    def reset(self) -> None:
        """Test-only: clears all tracked usage."""
        self._minute_window.clear()
        self._day_key = None
        self._day_count = 0


_default_rate_limiter: Optional[SahmkRateLimiter] = None


def get_default_rate_limiter() -> SahmkRateLimiter:
    """Returns the process-wide SahmkRateLimiter, constructing it from
    src.market_data.config on first use. Every SahmkClient shares this
    same instance unless a caller explicitly passes its own."""
    global _default_rate_limiter
    if _default_rate_limiter is None:
        _default_rate_limiter = SahmkRateLimiter(
            max_per_minute=market_data_config.get_sahmk_max_requests_per_minute(),
            max_per_day=market_data_config.get_sahmk_max_requests_per_day(),
        )
    return _default_rate_limiter


def reset_default_rate_limiter() -> None:
    """Test-only: clears the singleton so the next get_default_rate_limiter()
    call rebuilds it from the current environment/config."""
    global _default_rate_limiter
    _default_rate_limiter = None
