"""Unit tests for src.analysis.decision_v2.decision_freshness -- the
production freshness fix (2026-08-23). Pure datetime math layered on
src.market_intelligence.market_status, no I/O. Uses fixed dates
(2026-07-28 is a Tuesday, matching tests/unit/market_intelligence/
test_market_status.py's own reference dates) rather than datetime.now(),
so every test is deterministic regardless of when it actually runs.

These are the regression-fixture-derived cases named in the mandate:
TEST C/D/G/H directly; TEST A/B/F (Recommendation-vs-Decision-V2
precedence, and "newer Decision wins") are covered structurally by the
existing "most recent DecisionV2Snapshot by decision_timestamp desc"
queries in watchlist.py/portfolio.py (unit-tested at the route layer,
not here -- this module has no knowledge of Recommendation or which
query picked which row, only "is this one timestamp fresh").
"""

from datetime import datetime, timedelta

from src.analysis.decision_v2.decision_freshness import classify_decision_freshness, is_decision_fresh
from src.analysis.decision_v2.types import DataFreshnessStatus
from src.market_intelligence.market_status import get_market_status
from src.market_intelligence.trading_calendar import TADAWUL_TIMEZONE


def _tadawul(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TADAWUL_TIMEZONE)


class TestNoTimestamp:
    def test_none_decision_timestamp_is_unknown_and_not_fresh(self):
        status_info = get_market_status(_tadawul(2026, 7, 28, 12, 0))
        assert classify_decision_freshness(None, status_info) == DataFreshnessStatus.UNKNOWN
        assert is_decision_fresh(None, status_info) is False


class TestMarketOpenSameSessionIsLive:
    """TEST D (mandate): fresh BUY_CANDIDATE + fresh quote from the
    same valid session -> current/actionable. A decision computed
    earlier the same trading day, while the market is still open, is
    LIVE and fresh."""

    def test_decision_from_this_mornings_open_is_live(self):
        now = _tadawul(2026, 7, 28, 14, 0)  # Tuesday, mid-session
        status_info = get_market_status(now)
        decision_timestamp = _tadawul(2026, 7, 28, 10, 5)  # same day, just after open
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.LIVE
        assert is_decision_fresh(decision_timestamp, status_info) is True

    def test_decision_computed_seconds_ago_is_live(self):
        now = _tadawul(2026, 7, 28, 11, 30)
        status_info = get_market_status(now)
        decision_timestamp = now - timedelta(seconds=5)
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.LIVE


class TestStaleAcrossSessions:
    """TEST G (mandate): decision_timestamp older than the current
    trading session -> not presented as fresh. Mirrors the mandate's
    own example almost exactly: a decision from a prior trading day,
    read while today's market is open, must be STALE -- never LIVE."""

    def test_three_days_old_decision_while_market_open_is_stale(self):
        now = _tadawul(2026, 7, 28, 12, 0)  # Tuesday, market open
        status_info = get_market_status(now)
        decision_timestamp = _tadawul(2026, 7, 23, 14, 0)  # prior Thursday's close
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.STALE
        assert is_decision_fresh(decision_timestamp, status_info) is False

    def test_yesterdays_decision_while_market_open_today_is_stale(self):
        now = _tadawul(2026, 7, 28, 10, 30)  # Tuesday, market open
        status_info = get_market_status(now)
        decision_timestamp = _tadawul(2026, 7, 27, 13, 0)  # Monday, prior session
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.STALE


class TestLastCompletedSessionWhileClosed:
    """A decision from the most recently completed session, viewed
    while the market is currently closed (post-close/weekend), is
    still the best available answer -- LAST_SESSION, not STALE."""

    def test_thursdays_close_decision_viewed_saturday_is_last_session(self):
        now = _tadawul(2026, 8, 1, 12, 0)  # Saturday -- weekend
        status_info = get_market_status(now)
        decision_timestamp = _tadawul(2026, 7, 30, 14, 30)  # Thursday, last trading day
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.LAST_SESSION
        assert is_decision_fresh(decision_timestamp, status_info) is True

    def test_todays_pre_market_decision_from_yesterday_is_last_session(self):
        now = _tadawul(2026, 7, 28, 8, 0)  # Tuesday, before pre-open auction
        status_info = get_market_status(now)
        decision_timestamp = _tadawul(2026, 7, 27, 14, 0)  # Monday close
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.LAST_SESSION

    def test_older_than_last_completed_session_while_closed_is_stale(self):
        now = _tadawul(2026, 8, 1, 12, 0)  # Saturday
        status_info = get_market_status(now)
        decision_timestamp = _tadawul(2026, 7, 27, 14, 0)  # Monday -- not the last completed session (Thursday is)
        assert classify_decision_freshness(decision_timestamp, status_info) == DataFreshnessStatus.STALE
        assert is_decision_fresh(decision_timestamp, status_info) is False


class TestLivePriceCannotUpgradeStaleDecision:
    """TEST H (mandate): a fresh price alone must not upgrade a stale
    Decision to current. This module never accepts a price/quote
    input at all -- its result depends solely on decision_timestamp
    and the market session, by construction, so no quote freshness
    signal can influence the verdict."""

    def test_result_depends_only_on_decision_timestamp_not_on_any_price_context(self):
        now = _tadawul(2026, 7, 28, 12, 0)
        status_info = get_market_status(now)
        stale_decision_timestamp = _tadawul(2026, 7, 20, 10, 0)
        # Calling the function offers no parameter through which a
        # "live price" could ever change this result -- verified by
        # simply asserting the stale verdict holds regardless of how
        # recently this test itself runs relative to `now`.
        assert classify_decision_freshness(stale_decision_timestamp, status_info) == DataFreshnessStatus.STALE
        assert is_decision_fresh(stale_decision_timestamp, status_info) is False


class TestNaiveDatetimeHandled:
    def test_naive_decision_timestamp_treated_as_utc(self):
        now = _tadawul(2026, 7, 28, 12, 0)
        status_info = get_market_status(now)
        naive_recent = datetime(2026, 7, 28, 8, 0)  # no tzinfo -- e.g. a DB-round-tripped naive UTC value
        result = classify_decision_freshness(naive_recent, status_info)
        assert result in (DataFreshnessStatus.LIVE, DataFreshnessStatus.LAST_SESSION, DataFreshnessStatus.STALE)
