"""Production freshness fix (2026-08-23): classifies how recently a
*decision* (not a price quote) was actually computed, relative to the
current/most-recent Tadawul trading session -- a deliberately separate
concept from `DecisionV2Result.data_freshness_status`, which measures
the age of the underlying price/quote data a decision was computed
from (see `engine.py`'s freshness block, ~line 317). A decision can be
`data_freshness_status=LIVE` (it was built from a live quote at the
moment it was computed) while itself being three days old -- this
module answers "is the decision itself still current for today's
session", never "was the price live when it was computed".

Reuses the existing `DataFreshnessStatus` taxonomy (LIVE/LAST_SESSION/
STALE/UNKNOWN) rather than inventing new terminology, and the existing
`src.market_intelligence.market_status` Tadawul session/calendar
utility rather than re-deriving trading-day/session-boundary logic --
per the "use an existing mechanism, do not build a new market
calendar" constraint this module was written under.

A decision is judged against the *session it belongs to*, not against
elapsed wall-clock hours: a decision made at 14:55 during Thursday's
close is still the right answer at 09:00 Sunday pre-market (no newer
session has completed yet), while a decision made at 09:05 this
morning is already STALE if it is now Sunday 14:00 open and no fresher
evaluation exists for the symbol -- because a new trading day is
already the operative session context.
"""

from datetime import datetime, timezone
from typing import Optional

from src.analysis.decision_v2.types import DataFreshnessStatus
from src.market_intelligence.market_status import MarketSessionStatus, MarketStatusInfo, get_market_status
from src.market_intelligence.trading_calendar import TADAWUL_TIMEZONE

_ACTIVE_SESSION_STATUSES = frozenset(
    {
        MarketSessionStatus.OPEN,
        MarketSessionStatus.PRE_OPEN_AUCTION,
        MarketSessionStatus.CLOSING_AUCTION,
        MarketSessionStatus.CLOSING_PRICE_TRADING,
    }
)


def _session_date(decision_timestamp: datetime):
    if decision_timestamp.tzinfo is None:
        decision_timestamp = decision_timestamp.replace(tzinfo=timezone.utc)
    return decision_timestamp.astimezone(TADAWUL_TIMEZONE).date()


def classify_decision_freshness(
    decision_timestamp: Optional[datetime],
    market_status: Optional[MarketStatusInfo] = None,
) -> DataFreshnessStatus:
    """Whether `decision_timestamp` (a real `DecisionV2Snapshot.
    decision_timestamp` / `RadarOpportunity.emitted_at` / equivalent)
    belongs to the session that is currently the operative one for
    live trading -- today's in-progress session while the market is
    open/in an auction phase, otherwise the most recently completed
    session (`MarketStatusInfo.last_completed_session_date`, which
    already correctly returns "yesterday" while today's session is
    still running and "today" once today's session has closed).

    No `decision_timestamp` -> UNKNOWN (never fabricated as fresh).
    Same session as the operative one -> LIVE while that session is
    actively trading, LAST_SESSION once it has closed. Any older
    session -> STALE, regardless of how "live" the price data used to
    compute it was at the time.
    """
    if decision_timestamp is None:
        return DataFreshnessStatus.UNKNOWN

    info = market_status or get_market_status()
    operative_session_date = (
        info.server_time_riyadh.date() if info.status in _ACTIVE_SESSION_STATUSES else info.last_completed_session_date
    )
    if operative_session_date is None:
        return DataFreshnessStatus.UNKNOWN

    if _session_date(decision_timestamp) != operative_session_date:
        return DataFreshnessStatus.STALE

    return DataFreshnessStatus.LIVE if info.status in _ACTIVE_SESSION_STATUSES else DataFreshnessStatus.LAST_SESSION


def is_decision_fresh(decision_timestamp: Optional[datetime], market_status: Optional[MarketStatusInfo] = None) -> bool:
    """True only for LIVE/LAST_SESSION -- i.e. the decision may still
    be presented as a current actionable signal. STALE/UNKNOWN must
    not be shown as actionable-current (the mandate's non-negotiable
    rule)."""
    status = classify_decision_freshness(decision_timestamp, market_status)
    return status in (DataFreshnessStatus.LIVE, DataFreshnessStatus.LAST_SESSION)
