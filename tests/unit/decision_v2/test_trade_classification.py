"""Unit tests for trade_classification.py -- trade-type and
entry-status derivation, isolated from the full DecisionEngineV2 path
(covered separately in test_engine.py's TestPhase2ACanonicalFields)."""

from src.analysis.decision_v2.trade_classification import classify_entry_status, classify_trade_type
from src.analysis.decision_v2.types import Decision, EntryStatus, TradeType


class TestClassifyTradeType:
    def test_returns_none_without_a_holding_period(self):
        trade_type, rationale = classify_trade_type("SHORT_TERM", None, None, 70.0, 50.0)
        assert trade_type is None
        assert rationale != ""

    def test_short_term_strong_momentum_is_a_short_swing(self):
        trade_type, _ = classify_trade_type("SHORT_TERM", 1, 15, 80.0, 50.0)
        assert trade_type is TradeType.SHORT_SWING_2_5_DAYS

    def test_short_term_weak_momentum_is_a_weekly_swing(self):
        trade_type, _ = classify_trade_type("SHORT_TERM", 1, 15, 30.0, 50.0)
        assert trade_type is TradeType.WEEKLY_SWING

    def test_medium_term_high_volatility_is_a_swing_trade(self):
        trade_type, _ = classify_trade_type("MEDIUM_TERM", 7, 90, 50.0, 80.0)
        assert trade_type is TradeType.SWING_TRADE

    def test_medium_term_low_volatility_is_a_monthly_investment(self):
        trade_type, _ = classify_trade_type("MEDIUM_TERM", 7, 90, 50.0, 30.0)
        assert trade_type is TradeType.MONTHLY_INVESTMENT

    def test_long_term_short_range_is_medium_term_investment(self):
        trade_type, _ = classify_trade_type("LONG_TERM", 30, 100, None, None)
        assert trade_type is TradeType.MEDIUM_TERM_INVESTMENT

    def test_long_term_full_range_is_long_term_investment(self):
        trade_type, _ = classify_trade_type("LONG_TERM", 30, 180, None, None)
        assert trade_type is TradeType.LONG_TERM_INVESTMENT

    def test_scalp_and_intraday_are_never_returned(self):
        """No intraday time-series is ingested -- these two labels must
        never be assigned, only ever defined for API compatibility."""
        for horizon, min_d, max_d in [("SHORT_TERM", 1, 15), ("MEDIUM_TERM", 7, 90), ("LONG_TERM", 30, 180)]:
            for momentum in (None, 10.0, 50.0, 90.0):
                for volatility in (None, 10.0, 50.0, 90.0):
                    trade_type, _ = classify_trade_type(horizon, min_d, max_d, momentum, volatility)
                    assert trade_type not in (TradeType.SCALP, TradeType.INTRADAY)

    def test_unknown_horizon_returns_none(self):
        trade_type, rationale = classify_trade_type("UNKNOWN_BUCKET", 1, 15, 50.0, 50.0)
        assert trade_type is None


class TestClassifyEntryStatus:
    def test_buy_candidate_is_ready_now(self):
        status, explanation = classify_entry_status(Decision.BUY_CANDIDATE, 100.0, 102.0, False)
        assert status is EntryStatus.READY_NOW
        assert explanation != ""

    def test_strong_buy_candidate_is_ready_now(self):
        status, _ = classify_entry_status(Decision.STRONG_BUY_CANDIDATE, 100.0, 102.0, False)
        assert status is EntryStatus.READY_NOW

    def test_wait_for_entry_with_missed_zone_is_missed_entry(self):
        status, _ = classify_entry_status(Decision.WAIT_FOR_ENTRY, 105.0, 102.0, True)
        assert status is EntryStatus.MISSED_ENTRY

    def test_wait_for_entry_without_missed_zone_is_wait_for_pullback(self):
        status, _ = classify_entry_status(Decision.WAIT_FOR_ENTRY, 100.0, 102.0, False)
        assert status is EntryStatus.WAIT_FOR_PULLBACK

    def test_watch_is_near_entry(self):
        status, _ = classify_entry_status(Decision.WATCH, 100.0, 102.0, False)
        assert status is EntryStatus.NEAR_ENTRY

    def test_reject_hold_reduce_exit_and_insufficient_data_are_not_suitable(self):
        for decision in (Decision.REJECT, Decision.HOLD, Decision.REDUCE, Decision.EXIT, Decision.INSUFFICIENT_DATA):
            status, _ = classify_entry_status(decision, 100.0, 102.0, False)
            assert status is EntryStatus.NOT_SUITABLE

    def test_conditional_on_breakout_is_never_returned(self):
        """Requires a real breakout-pattern detector -- deferred to
        Phase 2F. Must never be assigned by this module today."""
        for decision in Decision:
            for missed in (True, False):
                status, _ = classify_entry_status(decision, 100.0, 102.0, missed)
                assert status is not EntryStatus.CONDITIONAL_ON_BREAKOUT
