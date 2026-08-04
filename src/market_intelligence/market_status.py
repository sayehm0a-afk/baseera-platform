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
(already encoded in trading_calendar), closing auction 15:00-15:10,
trading at the closing price 15:10-15:20. Every hour of a Sun-Thu
trading day is classified by one of these real, published windows
(PRE_MARKET before 09:30, POST_CLOSE after 15:20) -- CLOSED is kept in
the taxonomy for API back-compatibility and as an explicit fallback,
but is never actually returned for a trading weekday under this
schedule; Fri/Sat now report WEEKEND instead, since "closed because
it's the weekend" and "closed randomly outside session hours" are
different, useful pieces of information for the frontend/gates to
distinguish (Phase 1 Decision Engine V2's 9-state status requirement).

Disclosed gap (inherited from trading_calendar, restated here so a
caller of *this* module sees it too): no exchange holiday calendar is
integrated. On an actual Tadawul holiday that falls Sun-Thu, this will
incorrectly report a session state instead of "عطلة رسمية" -- there is
no data source wired into this codebase that could catch that case
today. UNKNOWN exists in the taxonomy for exactly this kind of
unresolvable case but is not returned by `get_market_status()` itself
today (every input to this pure function resolves to a real calendar
window); it is reserved for a future caller (e.g. once a holiday feed
exists) that needs to say "I cannot classify this" explicitly, and
`gates.py`'s `market_status_known` check already treats it as
not-known if it is ever passed through.
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
_CLOSING_PRICE_TRADING_END = time(15, 20)


class MarketSessionStatus(str, Enum):
    OPEN = "OPEN"
    PRE_MARKET = "PRE_MARKET"
    PRE_OPEN_AUCTION = "PRE_OPEN_AUCTION"
    CLOSING_AUCTION = "CLOSING_AUCTION"
    CLOSING_PRICE_TRADING = "CLOSING_PRICE_TRADING"
    POST_CLOSE = "POST_CLOSE"
    WEEKEND = "WEEKEND"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


_LABELS_AR = {
    MarketSessionStatus.OPEN: "السوق مفتوح",
    MarketSessionStatus.PRE_MARKET: "قبل الافتتاح",
    MarketSessionStatus.PRE_OPEN_AUCTION: "مزاد الافتتاح",
    MarketSessionStatus.CLOSING_AUCTION: "مزاد الإغلاق",
    MarketSessionStatus.CLOSING_PRICE_TRADING: "التداول على سعر الإغلاق",
    MarketSessionStatus.POST_CLOSE: "بعد الإغلاق",
    MarketSessionStatus.WEEKEND: "عطلة أسبوعية",
    MarketSessionStatus.CLOSED: "السوق مغلق",
    MarketSessionStatus.UNKNOWN: "حالة غير مؤكدة",
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

    if not is_trading_day:
        status = MarketSessionStatus.WEEKEND
    elif TADAWUL_SESSION_OPEN <= current_time < TADAWUL_SESSION_CLOSE:
        status = MarketSessionStatus.OPEN
    elif _PRE_OPEN_START <= current_time < TADAWUL_SESSION_OPEN:
        status = MarketSessionStatus.PRE_OPEN_AUCTION
    elif TADAWUL_SESSION_CLOSE <= current_time < _CLOSING_AUCTION_END:
        status = MarketSessionStatus.CLOSING_AUCTION
    elif _CLOSING_AUCTION_END <= current_time < _CLOSING_PRICE_TRADING_END:
        status = MarketSessionStatus.CLOSING_PRICE_TRADING
    elif current_time < _PRE_OPEN_START:
        status = MarketSessionStatus.PRE_MARKET
    else:
        status = MarketSessionStatus.POST_CLOSE

    return MarketStatusInfo(
        status=status,
        label_ar=_LABELS_AR[status],
        is_trading_day=is_trading_day,
        server_time_riyadh=local,
        seconds_until_next_open=seconds_until_next_open(local),
        seconds_until_close=seconds_until_close(local) if status == MarketSessionStatus.OPEN else None,
        last_completed_session_date=_last_completed_session_date(local),
    )
