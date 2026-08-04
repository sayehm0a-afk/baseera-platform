"""Unit tests for the 15 Decision Engine V2 publication gates
(src.analysis.decision_v2.gates) -- pure function tests over
`GateInputs`, no I/O, no dependency on TechnicalAnalysisEngine's real
indicator math (that integration is covered separately in
test_engine.py)."""

from src.analysis.decision.types import EntryQuality
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.gates import GateInputs, evaluate_decision
from src.analysis.decision_v2.types import Decision
from src.analysis.recommendation.types import Recommendation

TUNING = DecisionV2Tuning()


def _base_buy_inputs(**overrides) -> GateInputs:
    defaults = dict(
        has_technical=True,
        recommendation=Recommendation.BUY,
        direction=1,
        is_synthetic=False,
        data_age_hours=1.0,
        max_age_hours=24.0,
        price=100.0,
        entry_zone_low=97.0,
        entry_zone_high=101.0,
        stop_loss=94.0,
        target_1=110.0,
        risk_reward_ratio=2.0,
        min_risk_reward_ratio=1.0,
        average_traded_value=5_000_000.0,
        min_average_traded_value=1_000_000.0,
        atr_pct=0.02,
        excessive_volatility_pct=0.08,
        market_status_known=True,
        available_sub_score_count=6,
        fundamentals_available=True,
        news_available=True,
        entry_quality=EntryQuality.GOOD,
        price_missed_entry_zone=False,
        trend_momentum_conflict=None,
        volume_confirms_decision=True,
        change_percent=1.5,
        price_limit_proximity_pct=TUNING.price_limit_proximity_pct,
        risk_level="MEDIUM",
        strong_buy_minimum_confidence=TUNING.strong_buy_minimum_confidence,
        confidence_score=80.0,
        market_context_score=70.0,
    )
    defaults.update(overrides)
    return GateInputs(**defaults)


class TestBaselineMappings:
    def test_hold_maps_to_hold(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.HOLD, direction=0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.HOLD

    def test_sell_maps_to_reduce(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.SELL, direction=-1)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REDUCE

    def test_strong_sell_maps_to_exit(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.STRONG_SELL, direction=-1)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.EXIT

    def test_buy_with_everything_passing_is_buy_candidate(self):
        result = evaluate_decision(_base_buy_inputs(), TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_strong_buy_with_everything_passing_is_strong_buy_candidate(self):
        # Phase 2B: STRONG_BUY_CANDIDATE additionally requires full 8/8
        # sub-score coverage and a confidence floor -- override both
        # beyond the module's deliberately-partial (6/8) baseline.
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_BUY, available_sub_score_count=8, confidence_score=90.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.STRONG_BUY_CANDIDATE


class TestDataAuthenticityAndAvailability:
    def test_synthetic_data_is_rejected_regardless_of_everything_else(self):
        inputs = _base_buy_inputs(is_synthetic=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT
        assert any(g.name == "real_data_source" and not g.passed for g in result.gates)

    def test_missing_technical_data_is_insufficient_data(self):
        inputs = _base_buy_inputs(has_technical=False, recommendation=None, direction=0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA

    def test_no_recommendation_is_insufficient_data(self):
        inputs = _base_buy_inputs(recommendation=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA

    def test_invalid_price_is_insufficient_data(self):
        inputs = _base_buy_inputs(price=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA

    def test_negative_price_is_insufficient_data(self):
        inputs = _base_buy_inputs(price=-5.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA


class TestStaleData:
    def test_stale_data_downgrades_buy_to_watch_not_reject(self):
        inputs = _base_buy_inputs(data_age_hours=48.0, max_age_hours=24.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        assert any("بيانات" in w for w in result.warnings)

    def test_stale_data_does_not_block_hold(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.HOLD, direction=0, data_age_hours=48.0, max_age_hours=24.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.HOLD


class TestEntryZoneAndTargetOrdering:
    def test_entry_zone_low_above_high_is_rejected(self):
        inputs = _base_buy_inputs(entry_zone_low=105.0, entry_zone_high=95.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_missing_entry_zone_is_rejected(self):
        inputs = _base_buy_inputs(entry_zone_low=None, entry_zone_high=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_stop_above_entry_zone_low_is_rejected(self):
        inputs = _base_buy_inputs(stop_loss=99.0)  # entry_zone_low=97.0 -- stop must be < 97
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_target_below_entry_zone_high_is_rejected(self):
        inputs = _base_buy_inputs(target_1=100.5)  # entry_zone_high=101.0 -- target must be > 101
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT


class TestMissedEntry:
    def test_price_past_entry_zone_becomes_wait_for_entry(self):
        inputs = _base_buy_inputs(price_missed_entry_zone=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WAIT_FOR_ENTRY
        assert any("مطاردة" in w for w in result.warnings)


class TestRiskRewardAndLiquidity:
    def test_risk_reward_below_minimum_is_rejected(self):
        inputs = _base_buy_inputs(risk_reward_ratio=0.5, min_risk_reward_ratio=1.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_missing_risk_reward_is_rejected(self):
        inputs = _base_buy_inputs(risk_reward_ratio=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_liquidity_below_minimum_is_rejected(self):
        inputs = _base_buy_inputs(average_traded_value=100_000.0, min_average_traded_value=1_000_000.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_unknown_liquidity_does_not_block(self):
        inputs = _base_buy_inputs(average_traded_value=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE


class TestVolatilityAndEvidence:
    def test_excessive_volatility_downgrades_to_watch(self):
        inputs = _base_buy_inputs(atr_pct=0.15, excessive_volatility_pct=0.08)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH

    def test_single_indicator_confidence_downgrades_to_watch(self):
        inputs = _base_buy_inputs(available_sub_score_count=1)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH

    def test_poor_entry_quality_downgrades_to_watch_not_reject(self):
        inputs = _base_buy_inputs(entry_quality=EntryQuality.POOR)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH


class TestDisclosuresNeverBlock:
    def test_missing_fundamentals_does_not_block_a_valid_buy(self):
        inputs = _base_buy_inputs(fundamentals_available=False)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        assert any("أساسية" in d for d in result.disclosures)

    def test_missing_news_does_not_block_a_valid_buy(self):
        inputs = _base_buy_inputs(news_available=False)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        assert any("إخبارية" in d for d in result.disclosures)


class TestPhase2BTrendMomentumConsistencyGate:
    def test_conflicting_indicators_downgrades_to_watch(self):
        inputs = _base_buy_inputs(trend_momentum_conflict="الاتجاه العام إيجابي لكن الزخم الحالي ضعيف -- إشارات متعارضة.")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        assert any(g.name == "trend_momentum_consistency" and not g.passed for g in result.gates)
        assert any("متعارضة" in w for w in result.warnings)

    def test_no_conflict_leaves_the_buy_candidate_untouched(self):
        inputs = _base_buy_inputs(trend_momentum_conflict=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        assert any(g.name == "trend_momentum_consistency" and g.passed for g in result.gates)


class TestPhase2BVolumeQualityGate:
    def test_volume_contradicting_the_decision_downgrades_to_watch(self):
        inputs = _base_buy_inputs(volume_confirms_decision=False)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        assert any(g.name == "volume_quality" and not g.passed for g in result.gates)

    def test_volume_confirming_the_decision_does_not_block(self):
        inputs = _base_buy_inputs(volume_confirms_decision=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_unknown_volume_confirmation_does_not_block(self):
        """None means "no OBV history yet," not a contradiction --
        must never be treated as a fail."""
        inputs = _base_buy_inputs(volume_confirms_decision=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE


class TestPhase2BConfidenceCalibrationGate:
    def test_strong_buy_with_full_coverage_and_high_confidence_stays_strong(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_BUY, available_sub_score_count=8, confidence_score=90.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.STRONG_BUY_CANDIDATE

    def test_strong_buy_with_partial_coverage_downgrades_to_buy_candidate(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_BUY, available_sub_score_count=6, confidence_score=90.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        assert any(g.name == "confidence_calibration_minimum" and not g.passed for g in result.gates)

    def test_strong_buy_below_the_confidence_floor_downgrades_to_buy_candidate(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_BUY, available_sub_score_count=8, confidence_score=50.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_confidence_calibration_gate_is_never_evaluated_for_a_plain_buy(self):
        """Only STRONG_BUY_CANDIDATE is held to this stricter bar."""
        inputs = _base_buy_inputs(recommendation=Recommendation.BUY, available_sub_score_count=1, confidence_score=10.0)
        result = evaluate_decision(inputs, TUNING)
        # A plain BUY with only 1/8 coverage is downgraded to WATCH by
        # the existing multi_factor_evidence gate, never REJECT -- and
        # never carries a confidence_calibration_minimum entry at all.
        assert not any(g.name == "confidence_calibration_minimum" for g in result.gates)


class TestPhase2BPriceLimitProximityGate:
    def test_large_daily_move_is_flagged_as_a_caution_not_a_block(self):
        inputs = _base_buy_inputs(change_percent=9.5)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        gate = next(g for g in result.gates if g.name == "price_limit_proximity")
        assert gate.passed is False
        assert gate.blocking is False
        assert any("تحرك" in w for w in result.warnings)

    def test_normal_daily_move_passes_cleanly(self):
        inputs = _base_buy_inputs(change_percent=1.2)
        result = evaluate_decision(inputs, TUNING)
        gate = next(g for g in result.gates if g.name == "price_limit_proximity")
        assert gate.passed is True

    def test_unknown_change_percent_passes_cleanly(self):
        inputs = _base_buy_inputs(change_percent=None)
        result = evaluate_decision(inputs, TUNING)
        gate = next(g for g in result.gates if g.name == "price_limit_proximity")
        assert gate.passed is True


class TestPhase2BInformationalGatesAlwaysPresent:
    def test_quote_timestamp_known_gate_present(self):
        result = evaluate_decision(_base_buy_inputs(data_age_hours=1.0), TUNING)
        assert any(g.name == "quote_timestamp_known" and g.passed for g in result.gates)

    def test_quote_timestamp_unknown_is_reported_not_blocked(self):
        result = evaluate_decision(_base_buy_inputs(data_age_hours=None), TUNING)
        gate = next(g for g in result.gates if g.name == "quote_timestamp_known")
        assert gate.passed is False
        assert gate.blocking is False

    def test_market_context_gate_present_when_score_available(self):
        result = evaluate_decision(_base_buy_inputs(market_context_score=75.0), TUNING)
        assert any(g.name == "market_context" for g in result.gates)

    def test_stale_recommendation_gate_is_honestly_not_evaluated(self):
        result = evaluate_decision(_base_buy_inputs(), TUNING)
        gate = next(g for g in result.gates if g.name == "stale_recommendation")
        assert gate.passed is True
        assert gate.blocking is False
        assert "غير مطبّق" in gate.detail

    def test_duplicate_signal_gate_is_honestly_not_evaluated(self):
        result = evaluate_decision(_base_buy_inputs(), TUNING)
        gate = next(g for g in result.gates if g.name == "duplicate_suppression")
        assert gate.passed is True
        assert gate.blocking is False

    def test_risk_warning_disclosed_for_high_risk(self):
        result = evaluate_decision(_base_buy_inputs(risk_level="HIGH"), TUNING)
        gate = next(g for g in result.gates if g.name == "risk_warning_disclosed")
        assert gate.passed is True
        assert "مرتفع" in gate.detail

    def test_risk_warning_states_the_level_for_low_medium_risk(self):
        result = evaluate_decision(_base_buy_inputs(risk_level="LOW"), TUNING)
        gate = next(g for g in result.gates if g.name == "risk_warning_disclosed")
        assert "LOW" in gate.detail


class TestPhase2BStrongBuyIsStricterThanBuy:
    """Direct regression for the Product Owner rule: a شراء قوي
    decision must require strictly more than a plain شراء."""

    def test_a_setup_good_enough_for_buy_can_fail_to_reach_strong_buy(self):
        buy_inputs = _base_buy_inputs(
            recommendation=Recommendation.BUY, available_sub_score_count=6, confidence_score=80.0,
        )
        strong_inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_BUY, available_sub_score_count=6, confidence_score=80.0,
        )
        buy_result = evaluate_decision(buy_inputs, TUNING)
        strong_result = evaluate_decision(strong_inputs, TUNING)
        assert buy_result.decision is Decision.BUY_CANDIDATE
        assert strong_result.decision is Decision.BUY_CANDIDATE  # downgraded, not STRONG_BUY_CANDIDATE
