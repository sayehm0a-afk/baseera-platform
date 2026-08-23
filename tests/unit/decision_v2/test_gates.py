"""Unit tests for the 15 Decision Engine V2 publication gates
(src.analysis.decision_v2.gates) -- pure function tests over
`GateInputs`, no I/O, no dependency on TechnicalAnalysisEngine's real
indicator math (that integration is covered separately in
test_engine.py)."""

from src.analysis.decision.types import EntryQuality
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.gates import GateInputs, evaluate_decision
from src.analysis.decision_v2.types import Decision, GateStatus
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
        ohlcv_latest_bar_age_days=1.0,
        max_ohlcv_staleness_days=5.0,
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
        market_risk_entry_permitted=True,
        market_risk_label_ar="محايد",
    )
    defaults.update(overrides)
    return GateInputs(**defaults)


class TestConfidenceCalibrationGate:
    """Phase 3 area 2 structural repair: `confidence_calibration_applied`
    is the one gate `calibrated_success_probability` can affect -- a
    caution-level downgrade to WATCH, never a silent overwrite of
    `confidence_score` itself (this gate never touches that field)."""

    def test_no_calibration_applied_is_not_evaluated_and_unaffected(self):
        """Mandate proof C: the safe fallback -- omitting
        calibrated_success_probability (every caller before this
        repair, and the honest state until a model is active) leaves
        the decision completely unaffected."""
        inputs = _base_buy_inputs()
        result = evaluate_decision(inputs, TUNING)
        gate = next(g for g in result.gates if g.name == "confidence_calibration_applied")
        assert gate.status is GateStatus.NOT_EVALUATED
        assert result.decision is Decision.BUY_CANDIDATE

    def test_calibration_above_threshold_passes(self):
        inputs = _base_buy_inputs(calibrated_success_probability=0.6, min_calibrated_success_probability=0.35)
        result = evaluate_decision(inputs, TUNING)
        gate = next(g for g in result.gates if g.name == "confidence_calibration_applied")
        assert gate.status is GateStatus.PASS
        assert result.decision is Decision.BUY_CANDIDATE

    def test_calibration_below_threshold_downgrades_to_watch(self):
        """Mandate proof D: a mandatory condition genuinely failing --
        a real, poor calibrated probability -- changes the decision."""
        inputs = _base_buy_inputs(calibrated_success_probability=0.1, min_calibrated_success_probability=0.35)
        result = evaluate_decision(inputs, TUNING)
        gate = next(g for g in result.gates if g.name == "confidence_calibration_applied")
        assert gate.status is GateStatus.FAIL
        assert result.decision is Decision.WATCH

    def test_calibration_never_overwrites_confidence_score_itself(self):
        """`GateInputs.confidence_score` (the raw value) is untouched
        by this gate regardless of the calibrated value -- calibration
        gates the decision, it never silently rewrites the raw
        confidence this engine reports."""
        inputs = _base_buy_inputs(
            confidence_score=80.0, calibrated_success_probability=0.1, min_calibrated_success_probability=0.35,
        )
        assert inputs.confidence_score == 80.0


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


class TestOhlcvStaleness:
    """Distinct from TestStaleData above: data_age_hours/max_age_hours
    track the scan/live-quote's own recency (always fresh -- the
    current price is fetched live regardless of ingestion health);
    ohlcv_latest_bar_age_days/max_ohlcv_staleness_days track whether
    the multi-day daily-bar history the technical sub-scores are
    computed from has actually kept up, which a live quote fetch says
    nothing about. Mirrors src.market_intelligence.publication_gate's
    identical _ohlcv_staleness_gate for the legacy scan path."""

    def test_stale_ohlcv_history_downgrades_buy_to_watch_not_reject(self):
        inputs = _base_buy_inputs(ohlcv_latest_bar_age_days=12.0, max_ohlcv_staleness_days=5.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        assert any(g.name == "ohlcv_staleness" and not g.passed for g in result.gates)

    def test_fresh_ohlcv_history_passes_and_stays_buy_candidate(self):
        inputs = _base_buy_inputs(ohlcv_latest_bar_age_days=1.0, max_ohlcv_staleness_days=5.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        gate = next(g for g in result.gates if g.name == "ohlcv_staleness")
        assert gate.status is GateStatus.PASS

    def test_untracked_ohlcv_age_is_not_evaluated_not_blocked(self):
        inputs = _base_buy_inputs(ohlcv_latest_bar_age_days=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        gate = next(g for g in result.gates if g.name == "ohlcv_staleness")
        assert gate.status is GateStatus.NOT_EVALUATED

    def test_stale_ohlcv_history_does_not_block_hold(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.HOLD, direction=0,
            ohlcv_latest_bar_age_days=12.0, max_ohlcv_staleness_days=5.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.HOLD

    def test_stale_ohlcv_history_does_not_block_exit(self):
        """A defensive SELL-side action must not be suppressed just
        because the technical read behind it rests on old bars --
        exiting is the safer action, not one to discourage."""
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_SELL, direction=-1,
            ohlcv_latest_bar_age_days=12.0, max_ohlcv_staleness_days=5.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.EXIT


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
        """Mandate proof A: mild missed entry (price_severely_missed_
        entry_zone defaults to False) retains the exact prior
        WAIT_FOR_ENTRY behavior, unchanged by the Phase 3
        decision-authority repair."""
        inputs = _base_buy_inputs(price_missed_entry_zone=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WAIT_FOR_ENTRY
        assert any("مطاردة" in w for w in result.warnings)
        gate = next(g for g in result.gates if g.name == "entry_not_missed")
        assert gate.status is GateStatus.FAIL


class TestSevereAntiChase:
    """Phase 3 decision-authority repair: severity of an entry-zone
    overrun now has real decision consequence, using the already-
    computed structure.price_severely_missed_entry_zone signal. The
    prior REJECT proposal was explicitly rejected on review (semantic
    collisions with src.api.routes.portfolio._HOLDER_GUIDANCE_MAP's
    REJECT->EXIT mapping and the frontend's REJECT->sell/red badge
    color) -- Decision.WATCH is used instead, per that review."""

    def test_severe_missed_entry_becomes_watch(self):
        """Mandate proof B."""
        inputs = _base_buy_inputs(price_missed_entry_zone=True, price_severely_missed_entry_zone=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        gate = next(g for g in result.gates if g.name == "entry_not_missed")
        assert gate.status is GateStatus.FAIL

    def test_severe_missed_entry_never_produces_reject_exit_or_reduce(self):
        """Mandate proof C: severe anti-chase must never imply SELL,
        REDUCE, EXIT, or a bearish/invalidated-setup semantic -- this
        is a bullish overrun, not a broken trade."""
        inputs = _base_buy_inputs(price_missed_entry_zone=True, price_severely_missed_entry_zone=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision not in (Decision.REJECT, Decision.EXIT, Decision.REDUCE)
        assert result.decision is Decision.WATCH

    def test_severe_missed_entry_does_not_affect_sell_side_decisions(self):
        """Mandate proof G (anti-chase half): SELL-like recommendations
        never reach the BUY-branch entry-zone gates at all -- direction
        is negative, so price_missed_entry_zone/price_severely_missed_
        entry_zone are irrelevant and the base-recommendation mapping
        applies unchanged."""
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_SELL, direction=-1,
            price_missed_entry_zone=True, price_severely_missed_entry_zone=True,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.EXIT

    def test_mild_and_severe_are_distinguished_only_by_the_severity_flag(self):
        """Sanity check that the two branches are genuinely reachable
        and distinct from the identical base inputs."""
        mild = evaluate_decision(
            _base_buy_inputs(price_missed_entry_zone=True, price_severely_missed_entry_zone=False), TUNING,
        )
        severe = evaluate_decision(
            _base_buy_inputs(price_missed_entry_zone=True, price_severely_missed_entry_zone=True), TUNING,
        )
        assert mild.decision is Decision.WAIT_FOR_ENTRY
        assert severe.decision is Decision.WATCH


class TestFailedBreakoutGate:
    """Phase 3 decision-authority repair: FAILED_BREAKOUT is real
    contradicting technical evidence for a BUY thesis right now --
    downgrades to WATCH (never REJECT), mirroring the identical
    FAIL->WATCH pattern trend_momentum_consistency/volume_quality
    already use. Every other breakout_status value, including the
    safe default NOT_APPLICABLE, must PASS through unaffected."""

    def test_failed_breakout_downgrades_buy_candidate_to_watch(self):
        """Mandate proof E."""
        inputs = _base_buy_inputs(breakout_status="FAILED_BREAKOUT")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        gate = next(g for g in result.gates if g.name == "breakout_not_failed")
        assert gate.status is GateStatus.FAIL

    def test_failed_breakout_downgrades_strong_buy_too(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_BUY, available_sub_score_count=8, confidence_score=90.0,
            breakout_status="FAILED_BREAKOUT",
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH

    def test_not_applicable_default_is_byte_identical_to_pre_repair(self):
        """Mandate proof F (default case): omitting breakout_status
        entirely (every caller before this repair) must produce the
        exact same decision and gate list shape as today."""
        inputs = _base_buy_inputs()
        assert inputs.breakout_status == "NOT_APPLICABLE"
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        gate = next(g for g in result.gates if g.name == "breakout_not_failed")
        assert gate.status is GateStatus.PASS

    def test_confirmed_breakout_unaffected(self):
        """Mandate proof F."""
        inputs = _base_buy_inputs(breakout_status="CONFIRMED_BREAKOUT")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_early_breakout_unaffected(self):
        """Mandate proof F."""
        inputs = _base_buy_inputs(breakout_status="EARLY_BREAKOUT")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_unconfirmed_breakout_unaffected(self):
        """Mandate proof F."""
        inputs = _base_buy_inputs(breakout_status="UNCONFIRMED_BREAKOUT")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_sequence_unverified_unaffected(self):
        """Mandate proof F."""
        inputs = _base_buy_inputs(breakout_status="SEQUENCE_UNVERIFIED")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_failed_breakout_does_not_affect_hold(self):
        """Mandate proof G: HOLD returns before the BUY-like branch is
        ever reached, so breakout_status is irrelevant."""
        inputs = _base_buy_inputs(recommendation=Recommendation.HOLD, direction=0, breakout_status="FAILED_BREAKOUT")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.HOLD

    def test_failed_breakout_does_not_affect_reduce(self):
        """Mandate proof G."""
        inputs = _base_buy_inputs(recommendation=Recommendation.SELL, direction=-1, breakout_status="FAILED_BREAKOUT")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REDUCE

    def test_failed_breakout_does_not_affect_exit(self):
        """Mandate proof G."""
        inputs = _base_buy_inputs(
            recommendation=Recommendation.STRONG_SELL, direction=-1, breakout_status="FAILED_BREAKOUT",
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.EXIT


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
        gate = next(g for g in result.gates if g.name == "liquidity")
        assert gate.status is GateStatus.NOT_EVALUATED


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
        gate = next(g for g in result.gates if g.name == "volume_quality")
        assert gate.status is GateStatus.NOT_EVALUATED


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
        assert gate.status is GateStatus.NOT_EVALUATED
        assert gate.passed is True
        assert gate.blocking is False
        assert "غير مطبّق" in gate.detail

    def test_duplicate_signal_gate_is_honestly_not_evaluated(self):
        result = evaluate_decision(_base_buy_inputs(), TUNING)
        gate = next(g for g in result.gates if g.name == "duplicate_suppression")
        assert gate.status is GateStatus.NOT_EVALUATED
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


class TestPhase2CMarketRiskPermitsEntryGate:
    def test_entry_blocked_downgrades_buy_to_watch(self):
        inputs = _base_buy_inputs(market_risk_entry_permitted=False, market_risk_label_ar="خروج دفاعي")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        gate = next(g for g in result.gates if g.name == "market_risk_permits_entry")
        assert gate.passed is False
        assert gate.blocking is True
        assert "خروج دفاعي" in gate.detail
        assert any("خروج دفاعي" in w for w in result.warnings)

    def test_entry_permitted_does_not_block_a_valid_buy(self):
        inputs = _base_buy_inputs(market_risk_entry_permitted=True, market_risk_label_ar="دخول قوي")
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        gate = next(g for g in result.gates if g.name == "market_risk_permits_entry")
        assert gate.passed is True
        assert gate.blocking is False

    def test_market_risk_gate_does_not_affect_hold_or_sell_side_decisions(self):
        hold_inputs = _base_buy_inputs(
            recommendation=Recommendation.HOLD, direction=0, market_risk_entry_permitted=False,
        )
        sell_inputs = _base_buy_inputs(
            recommendation=Recommendation.SELL, direction=-1, market_risk_entry_permitted=False,
        )
        assert evaluate_decision(hold_inputs, TUNING).decision is Decision.HOLD
        assert evaluate_decision(sell_inputs, TUNING).decision is Decision.REDUCE
