"""Unit tests for trade_classification.py -- trade-type and
entry-status derivation, isolated from the full DecisionEngineV2 path
(covered separately in test_engine.py's TestPhase2ACanonicalFields)."""

from src.analysis.decision_v2.trade_classification import (
    classify_entry_status,
    classify_high_quality_buy,
    classify_trade_type,
)
from src.analysis.decision_v2.types import DataFreshnessStatus, Decision, EntryStatus, TradeType


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
    """The 4th positional argument is `price_severely_missed_entry_zone`
    -- a magnitude-aware signal distinct from the plain "has price
    missed the zone at all" boolean that already decided
    `Decision.WAIT_FOR_ENTRY` itself (Gate 15, gates.py). Reusing that
    same plain boolean here was the anti-chase structural defect the
    audit found: reaching this WAIT_FOR_ENTRY branch already required
    it to be True, making the WAIT_FOR_PULLBACK case below
    unreachable. See `structure.price_severely_missed_entry_zone`."""

    def test_buy_candidate_is_ready_now(self):
        status, explanation = classify_entry_status(Decision.BUY_CANDIDATE, 100.0, 102.0, False)
        assert status is EntryStatus.READY_NOW
        assert explanation != ""

    def test_strong_buy_candidate_is_ready_now(self):
        status, _ = classify_entry_status(Decision.STRONG_BUY_CANDIDATE, 100.0, 102.0, False)
        assert status is EntryStatus.READY_NOW

    def test_wait_for_entry_severely_missed_is_missed_entry(self):
        status, _ = classify_entry_status(Decision.WAIT_FOR_ENTRY, 110.0, 102.0, True)
        assert status is EntryStatus.MISSED_ENTRY

    def test_wait_for_entry_not_severely_missed_is_wait_for_pullback(self):
        """The exact case that was unreachable before the fix: decision
        is already WAIT_FOR_ENTRY (price has run past the zone at
        least somewhat -- otherwise Gate 15 would never have produced
        this decision in the first place) but the overrun is not
        severe, so this is still a live setup worth waiting on."""
        status, explanation = classify_entry_status(Decision.WAIT_FOR_ENTRY, 103.0, 102.0, False)
        assert status is EntryStatus.WAIT_FOR_PULLBACK
        assert explanation != ""

    def test_both_entry_states_are_actually_reachable(self):
        """Mandate proof D: neither branch is dead code."""
        missed_status, _ = classify_entry_status(Decision.WAIT_FOR_ENTRY, 110.0, 102.0, True)
        pullback_status, _ = classify_entry_status(Decision.WAIT_FOR_ENTRY, 103.0, 102.0, False)
        assert missed_status is EntryStatus.MISSED_ENTRY
        assert pullback_status is EntryStatus.WAIT_FOR_PULLBACK

    def test_watch_is_near_entry(self):
        status, _ = classify_entry_status(Decision.WATCH, 100.0, 102.0, False)
        assert status is EntryStatus.NEAR_ENTRY

    def test_reject_hold_reduce_exit_and_insufficient_data_are_not_suitable(self):
        for decision in (Decision.REJECT, Decision.HOLD, Decision.REDUCE, Decision.EXIT, Decision.INSUFFICIENT_DATA):
            status, _ = classify_entry_status(decision, 100.0, 102.0, False)
            assert status is EntryStatus.NOT_SUITABLE

    def test_conditional_on_breakout_never_returned_without_breakout_evidence(self):
        """Without a `breakout_status` (the default), or with any
        status other than the two real, evidence-gated ones (Phase 3
        area 5), CONDITIONAL_ON_BREAKOUT must never be assigned."""
        non_triggering_statuses = [
            None, "NOT_APPLICABLE", "SEQUENCE_UNVERIFIED", "CONFIRMED_BREAKOUT", "FAILED_BREAKOUT",
        ]
        for decision in Decision:
            for missed in (True, False):
                for breakout_status in non_triggering_statuses:
                    status, _ = classify_entry_status(decision, 100.0, 102.0, missed, breakout_status=breakout_status)
                    assert status is not EntryStatus.CONDITIONAL_ON_BREAKOUT

    def test_watch_with_early_breakout_is_conditional_on_breakout(self):
        status, explanation = classify_entry_status(
            Decision.WATCH, 100.0, 102.0, False, breakout_status="EARLY_BREAKOUT"
        )
        assert status is EntryStatus.CONDITIONAL_ON_BREAKOUT
        assert explanation != ""

    def test_watch_with_unconfirmed_breakout_is_conditional_on_breakout(self):
        status, _ = classify_entry_status(
            Decision.WATCH, 100.0, 102.0, False, breakout_status="UNCONFIRMED_BREAKOUT"
        )
        assert status is EntryStatus.CONDITIONAL_ON_BREAKOUT

    def test_non_watch_decision_ignores_breakout_status(self):
        """CONDITIONAL_ON_BREAKOUT only ever overrides the WATCH path --
        every other decision path is unaffected by breakout_status."""
        status, _ = classify_entry_status(
            Decision.BUY_CANDIDATE, 100.0, 102.0, False, breakout_status="EARLY_BREAKOUT"
        )
        assert status is EntryStatus.READY_NOW


class TestClassifyHighQualityBuy:
    def _ideal_kwargs(self):
        return dict(
            decision=Decision.STRONG_BUY_CANDIDATE,
            confidence_score=80.0,
            data_freshness_status=DataFreshnessStatus.LIVE,
            entry_status=EntryStatus.READY_NOW,
            risk_reward_target_1=2.5,
            volume_confirms_decision=True,
            sector_strength_used=True,
            stock_vs_sector_relative_strength=0.3,
            breakout_status="NOT_APPLICABLE",
            warnings=[],
        )

    def test_all_conditions_met_is_high_quality(self):
        is_hq, explanation = classify_high_quality_buy(**self._ideal_kwargs())
        assert is_hq is True
        assert explanation != ""

    def test_sector_data_absent_does_not_disqualify(self):
        kwargs = self._ideal_kwargs()
        kwargs["sector_strength_used"] = False
        kwargs["stock_vs_sector_relative_strength"] = None
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is True

    def test_watch_decision_is_never_high_quality(self):
        kwargs = self._ideal_kwargs()
        kwargs["decision"] = Decision.WATCH
        is_hq, explanation = classify_high_quality_buy(**kwargs)
        assert is_hq is False
        assert explanation == ""

    def test_low_confidence_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["confidence_score"] = 60.0
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_stale_data_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["data_freshness_status"] = DataFreshnessStatus.STALE
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_not_ready_now_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["entry_status"] = EntryStatus.NEAR_ENTRY
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_weak_risk_reward_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["risk_reward_target_1"] = 1.2
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_missing_risk_reward_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["risk_reward_target_1"] = None
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_volume_not_confirming_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["volume_confirms_decision"] = False
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_volume_confirmation_absent_disqualifies(self):
        """Unlike sector strength, volume confirmation must be
        affirmatively True -- None is not treated the same as absent
        sector data, since OBV direction is core, always-computable
        evidence, not an optional data-availability leg."""
        kwargs = self._ideal_kwargs()
        kwargs["volume_confirms_decision"] = None
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_underperforming_sector_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["stock_vs_sector_relative_strength"] = -0.2
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_failed_breakout_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["breakout_status"] = "FAILED_BREAKOUT"
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False

    def test_confirmed_breakout_does_not_disqualify(self):
        kwargs = self._ideal_kwargs()
        kwargs["breakout_status"] = "CONFIRMED_BREAKOUT"
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is True

    def test_any_active_warning_disqualifies(self):
        kwargs = self._ideal_kwargs()
        kwargs["warnings"] = ["سيولة التداول في هذا السهم محدودة نسبيًا."]
        is_hq, _ = classify_high_quality_buy(**kwargs)
        assert is_hq is False
