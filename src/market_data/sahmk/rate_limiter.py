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
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional

from src.market_data import config as market_data_config
from src.market_data.sahmk.request_priority import BACKGROUND, CRITICAL

logger = logging.getLogger(__name__)


class SahmkRateLimitExceededError(Exception):
    """Raised when the configured daily quota is already spent for
    today (UTC). Fails fast rather than sleeping for up to 24h --
    callers (an ingestion job) should treat this as "stop for today,"
    not retry."""


class SahmkQuotaReservedForCriticalError(SahmkRateLimitExceededError):
    """Raised instead of SahmkRateLimitExceededError when a
    priority=BACKGROUND caller's request would dip into the portion of
    today's daily quota reserved for priority=CRITICAL callers (live
    Decision Engine / market-scan quote lookups). The daily quota
    itself is not exhausted -- only the part of it background work is
    allowed to spend. Callers (ingestion jobs, admin diagnostics)
    should treat this exactly like SahmkRateLimitExceededError ("stop
    this background work for today"), which is why it subclasses it --
    existing except SahmkRateLimitExceededError handlers keep working
    unchanged."""


class SahmkRateLimiter:
    """Sliding-window limiter: at most `max_per_minute` acquire() calls
    complete in any trailing 60s window. If `max_per_day` is set,
    acquire() also refuses (raising SahmkRateLimitExceededError) once
    that many calls have been made since the last UTC midnight.

    If `reserved_for_critical` is also set, it carves out the last
    `reserved_for_critical` requests of each day's `max_per_day` budget
    for priority=CRITICAL callers only (see request_priority.py):
    once `day_count >= max_per_day - reserved_for_critical`, a
    priority=BACKGROUND acquire() raises SahmkQuotaReservedForCriticalError
    instead of proceeding, while priority=CRITICAL acquire() keeps
    working until the full `max_per_day` is reached. This is what
    keeps a historical backfill or an admin diagnostic from spending
    the quota a live Tadawul-hours scan needs later the same day.
    """

    def __init__(
        self,
        max_per_minute: int,
        max_per_day: Optional[int] = None,
        reserved_for_critical: Optional[int] = None,
    ):
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        if max_per_day is not None and max_per_day <= 0:
            raise ValueError("max_per_day must be positive if set")
        if reserved_for_critical is not None:
            if max_per_day is None:
                raise ValueError("reserved_for_critical requires max_per_day to be set")
            if reserved_for_critical < 0:
                raise ValueError("reserved_for_critical must not be negative")
            if reserved_for_critical > max_per_day:
                raise ValueError("reserved_for_critical must not exceed max_per_day")
        self._max_per_minute = max_per_minute
        self._max_per_day = max_per_day
        self._reserved_for_critical = reserved_for_critical or 0
        self._minute_window: Deque[float] = deque()
        self._day_key: Optional[str] = None
        self._day_count = 0
        self._background_count = 0
        self._critical_count = 0
        self._lock = asyncio.Lock()

    async def acquire(self, priority: str = CRITICAL) -> None:
        """Blocks (sleeping, never busy-waiting) until a slot is free
        under the per-minute window, then reserves it. Raises
        immediately -- never sleeps -- if the daily quota (or, for a
        priority=BACKGROUND caller, the background-available portion
        of it) is already spent."""
        async with self._lock:
            self._roll_day_window_locked()
            if self._max_per_day is not None and self._day_count >= self._max_per_day:
                raise SahmkRateLimitExceededError(
                    f"SAHMK daily request quota ({self._max_per_day}) already reached for today (UTC)."
                )
            if (
                priority == BACKGROUND
                and self._max_per_day is not None
                and self._reserved_for_critical > 0
                and self._day_count >= (self._max_per_day - self._reserved_for_critical)
            ):
                raise SahmkQuotaReservedForCriticalError(
                    f"SAHMK daily quota: only the last {self._reserved_for_critical} of "
                    f"{self._max_per_day} today's requests remain, reserved for "
                    "live-market-critical operations -- refusing this background request."
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
            if priority == BACKGROUND:
                self._background_count += 1
            else:
                self._critical_count += 1

    def _roll_day_window_locked(self) -> None:
        today_key = datetime.now(timezone.utc).date().isoformat()
        if today_key != self._day_key:
            self._day_key = today_key
            self._day_count = 0
            self._background_count = 0
            self._critical_count = 0

    def get_status(self) -> Dict[str, object]:
        """Secret-free snapshot for admin/system-health diagnostics
        (never touches the network). Reflects this process's own
        tracked usage only -- see the module docstring on why this is
        not cross-process-coordinated."""
        self._roll_day_window_locked()
        remaining_total = (
            max(0, self._max_per_day - self._day_count) if self._max_per_day is not None else None
        )
        background_cap = (
            max(0, self._max_per_day - self._reserved_for_critical)
            if self._max_per_day is not None
            else None
        )
        remaining_background = (
            max(0, background_cap - self._day_count) if background_cap is not None else None
        )
        tomorrow_utc_midnight = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        return {
            "max_per_minute": self._max_per_minute,
            "max_per_day": self._max_per_day,
            "reserved_for_critical": self._reserved_for_critical,
            "requests_used_today": self._day_count,
            "critical_requests_used_today": self._critical_count,
            "background_requests_used_today": self._background_count,
            "remaining_today": remaining_total,
            "remaining_today_for_background": remaining_background,
            "requests_in_last_minute": len(self._minute_window),
            "day_window_key_utc": self._day_key,
            "resets_at_utc": tomorrow_utc_midnight.isoformat(),
        }

    def reset(self) -> None:
        """Test-only: clears all tracked usage."""
        self._minute_window.clear()
        self._day_key = None
        self._day_count = 0
        self._background_count = 0
        self._critical_count = 0


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
            reserved_for_critical=market_data_config.get_sahmk_reserved_for_critical_requests_per_day(),
        )
    return _default_rate_limiter


def reset_default_rate_limiter() -> None:
    """Test-only: clears the singleton so the next get_default_rate_limiter()
    call rebuilds it from the current environment/config."""
    global _default_rate_limiter
    _default_rate_limiter = None
