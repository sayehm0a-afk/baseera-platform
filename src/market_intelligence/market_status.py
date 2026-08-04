"""Tadawul market-status classification for the frontend's status
banner/pill (Practical Live-Market Test release).

Builds directly on the existing `trading_calendar` module (Sun-Thu
10:00-15:00 AST continuous session, no holiday calendar integrated --
see that module's own disclosed gap). This module adds two things
`trading_calendar` deliberately does not: (1) the pre-open and
closing-auction sub-states Tadawul's own published trading schedule
defines around the continuous session, and (2) a single Arabic-labeled
status value the frontend can render directly instead of re-deriving
one from booleans.

Tadawul's publicly published main-market session structure (stable for
years, not fetched live -- SAHMK's `/market/summary/` endpoint returns
an index snapshot, not an explicit machine-readable session-state
field, per docs/SAHMK_INTEGRATION.md's verified endpoint table):
pre-open order collection 09:30-10:00, continuous trading 10:00-15:00
(already encoded in trading_calendar), closing auction 15:00-15:10.
Outside 09:30-15:10 on a trading weekday, or on Fri/Sat, the market is
simply closed.

Disclosed gap (inherited from trading_calendar, restated here so a
caller of *this* module sees it too): no exchange holiday calendar is
integrated. On an actual Tadawul holiday that falls Sun-Thu, this will
incorrectly report a session state instead of "عطلة رسمية" -- there is
no data source wired into this codebase that could catch that case
today.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Optional

from src.market_intelligence.trading_calendar import (
    TADAWUL_SESSION_CLOSE,
    TADAWUL_SESSION_OPEN,
    TADAWUL_TIMEZONE,
    TADAWUL_TRADING_WEEKDAYS,
    seconds_until_close,
    seconds_until_next_open,
)


def _to_tadawul_time(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(TADAWUL_TIMEZONE)


_PRE_OPEN_START = time(9, 30)
_CLOSING_AUCTION_END = time(15, 10)


class MarketSessionStatus(str, Enum):
    OPEN = "OPEN"
    PRE_OPEN_AUCTION = "PRE_OPEN_AUCTION"
    CLOSING_AUCTION = "CLOSING_AUCTION"
    CLOSED = "CLOSED"


_LABELS_AR = {
    MarketSessionStatus.OPEN: "السوق مفتوح",
    MarketSessionStatus.PRE_OPEN_AUCTION: "مزاد الافتتاح",
    MarketSessionStatus.CLOSING_AUCTION: "مزاد الإغلاق",
    MarketSessionStatus.CLOSED: "السوق مغلق",
}


@dataclass(frozen=True)
class MarketStatusInfo:
    status: MarketSessionStatus
    label_ar: str
    is_trading_day: bool
    server_time_riyadh: datetime
    seconds_until_next_open: float
    seconds_until_close: Optional[float]
    last_completed_session_date: Optional[date]
    """The most recent Sun-Thu calendar date strictly before `now`
    whose session has already fully closed -- used by the frontend to
    say "prices reflect the <date> session" while the market is
    closed. None only if called with a `now` before this platform's
    epoch is meaningful, which never happens in practice."""
    holiday_calendar_disclosed_gap: str = (
        "لا يوجد تقويم للعطلات الرسمية لتداول متكامل في هذا الإصدار — "
        "قد تُعرض حالة تداول اعتيادية خطأً خلال عطلة رسمية تقع ضمن أيام "
        "الأحد إلى الخميس."
    )


def _last_completed_session_date(local_now: datetime) -> date:
    """The latest Sun-Thu date whose 15:10 closing-auction end is
    strictly before `local_now` (Tadawul local time)."""
    candidate = local_now.date()
    for _ in range(8):
        candidate_close = datetime.combine(candidate, _CLOSING_AUCTION_END, tzinfo=TADAWUL_TIMEZONE)
        if candidate.weekday() in TADAWUL_TRADING_WEEKDAYS and candidate_close <= local_now:
            return candidate
        candidate -= timedelta(days=1)
    # Unreachable in practice (mirrors trading_calendar's own guarantee
    # that every 7-day window contains a trading day); a defensive
    # fallback rather than a crash if it is ever somehow reached.
    return candidate


def get_market_status(now: Optional[datetime] = None) -> MarketStatusInfo:
    now = now or datetime.now(timezone.utc)
    local = _to_tadawul_time(now)
    is_trading_day = local.weekday() in TADAWUL_TRADING_WEEKDAYS
    current_time = local.time()

    if is_trading_day and TADAWUL_SESSION_OPEN <= current_time < TADAWUL_SESSION_CLOSE:
        status = MarketSessionStatus.OPEN
    elif is_trading_day and _PRE_OPEN_START <= current_time < TADAWUL_SESSION_OPEN:
        status = MarketSessionStatus.PRE_OPEN_AUCTION
    elif is_trading_day and TADAWUL_SESSION_CLOSE <= current_time < _CLOSING_AUCTION_END:
        status = MarketSessionStatus.CLOSING_AUCTION
    else:
        status = MarketSessionStatus.CLOSED

    return MarketStatusInfo(
        status=status,
        label_ar=_LABELS_AR[status],
        is_trading_day=is_trading_day,
        server_time_riyadh=local,
        seconds_until_next_open=seconds_until_next_open(local),
        seconds_until_close=seconds_until_close(local) if status == MarketSessionStatus.OPEN else None,
        last_completed_session_date=_last_completed_session_date(local),
    )
