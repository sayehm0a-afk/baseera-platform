"""Unit tests for evidence.py -- support/resistance derivation,
liquidity/accumulation evidence, trend labels, and ATR-based
target-time estimates."""

from src.analysis.decision_v2.evidence import (
    derive_accumulation_evidence,
    derive_support_resistance,
    estimated_days_to_all_targets,
    estimated_days_to_target,
    liquidity_quality_label,
    trend_direction_and_strength_labels,
)
from src.analysis.types import SupportResistanceLevels


class TestDeriveSupportResistance:
    def test_no_levels_returns_all_none(self):
        result = derive_support_resistance(100.0, None)
        assert result.nearest_support is None
        assert result.evidence_ar == ""

    def test_nearest_support_is_the_closest_level_below_price(self):
        levels = SupportResistanceLevels(support=[90.0, 95.0, 98.0], resistance=[105.0, 110.0])
        result = derive_support_resistance(100.0, levels)
        assert result.nearest_support == 98.0
        assert result.major_support == 90.0

    def test_nearest_resistance_is_the_closest_level_above_price(self):
        levels = SupportResistanceLevels(support=[90.0], resistance=[102.0, 108.0, 115.0])
        result = derive_support_resistance(100.0, levels)
        assert result.nearest_resistance == 102.0
        assert result.major_resistance == 115.0

    def test_breakout_and_breakdown_alias_nearest_levels(self):
        levels = SupportResistanceLevels(support=[95.0], resistance=[105.0])
        result = derive_support_resistance(100.0, levels)
        assert result.breakout_level == result.nearest_resistance
        assert result.breakdown_level == result.nearest_support

    def test_evidence_text_discloses_the_real_detection_method(self):
        levels = SupportResistanceLevels(support=[95.0], resistance=[105.0])
        result = derive_support_resistance(100.0, levels)
        assert "قمم" in result.evidence_ar or "قيعان" in result.evidence_ar

    def test_no_support_below_price_returns_none_not_a_fabricated_value(self):
        levels = SupportResistanceLevels(support=[105.0, 110.0], resistance=[120.0])
        result = derive_support_resistance(100.0, levels)
        assert result.nearest_support is None


class TestLiquidityQualityLabel:
    def test_unknown_when_score_missing(self):
        assert liquidity_quality_label(None) == "غير محددة"

    def test_high_liquidity_label(self):
        assert liquidity_quality_label(85.0) == "سيولة جيدة"

    def test_low_liquidity_label(self):
        assert liquidity_quality_label(10.0) == "سيولة محدودة"


class TestDeriveAccumulationEvidence:
    def test_none_score_produces_no_assessment(self):
        result = derive_accumulation_evidence(None, None, 1)
        assert result.accumulation_score is None
        assert result.assessment_ar == ""

    def test_high_obv_with_volume_spike_uses_cautious_accumulation_language(self):
        result = derive_accumulation_evidence(70.0, 2.0, 1)
        assert "تجميع" in result.assessment_ar
        assert "محتملة" in result.assessment_ar  # never "مؤكد" (confirmed)

    def test_low_obv_uses_cautious_distribution_language(self):
        result = derive_accumulation_evidence(30.0, None, 1)
        assert "توزيع" in result.assessment_ar
        assert "محتملة" in result.assessment_ar

    def test_neutral_obv_has_no_clear_signal(self):
        result = derive_accumulation_evidence(50.0, None, 1)
        assert "لا توجد إشارة" in result.assessment_ar

    def test_abnormal_volume_flag_requires_a_real_spike(self):
        assert derive_accumulation_evidence(50.0, 2.5, 1).abnormal_volume is True
        assert derive_accumulation_evidence(50.0, 1.0, 1).abnormal_volume is False
        assert derive_accumulation_evidence(50.0, None, 1).abnormal_volume is False

    def test_volume_confirms_decision_flips_with_direction(self):
        bullish_obv = 65.0
        long_result = derive_accumulation_evidence(bullish_obv, None, 1)
        short_result = derive_accumulation_evidence(bullish_obv, None, -1)
        assert long_result.volume_confirms_decision is True
        assert short_result.volume_confirms_decision is False

    def test_no_direction_leaves_confirmation_undetermined(self):
        result = derive_accumulation_evidence(65.0, None, 0)
        assert result.volume_confirms_decision is None


class TestTrendDirectionAndStrengthLabels:
    def test_bullish_trend_score(self):
        direction, _ = trend_direction_and_strength_labels(70.0, 20.0)
        assert direction == "صاعد"

    def test_bearish_trend_score(self):
        direction, _ = trend_direction_and_strength_labels(30.0, 20.0)
        assert direction == "هابط"

    def test_neutral_trend_score(self):
        direction, _ = trend_direction_and_strength_labels(50.0, 20.0)
        assert direction == "غير واضح"

    def test_missing_trend_score_is_unclear(self):
        direction, _ = trend_direction_and_strength_labels(None, 20.0)
        assert direction == "غير واضح"

    def test_strong_adx_strength_label(self):
        _, strength = trend_direction_and_strength_labels(70.0, 45.0)
        assert strength == "قوي جدًا"

    def test_weak_adx_strength_label(self):
        _, strength = trend_direction_and_strength_labels(70.0, 5.0)
        assert strength == "ضعيف"

    def test_missing_adx_is_undetermined(self):
        _, strength = trend_direction_and_strength_labels(70.0, None)
        assert strength == "غير محددة"


class TestEstimatedDaysToTarget:
    def test_real_atr_based_estimate(self):
        assert estimated_days_to_target(100.0, 110.0, 2.0) == 5

    def test_none_when_any_input_missing(self):
        assert estimated_days_to_target(None, 110.0, 2.0) is None
        assert estimated_days_to_target(100.0, None, 2.0) is None
        assert estimated_days_to_target(100.0, 110.0, None) is None

    def test_none_when_atr_non_positive(self):
        assert estimated_days_to_target(100.0, 110.0, 0.0) is None

    def test_zero_distance_is_zero_days(self):
        assert estimated_days_to_target(100.0, 100.0, 2.0) == 0

    def test_minimum_one_day_for_a_nonzero_distance(self):
        assert estimated_days_to_target(100.0, 100.5, 5.0) == 1

    def test_estimated_days_to_all_targets_preserves_order_and_nones(self):
        result = estimated_days_to_all_targets(100.0, [110.0, None, 130.0], 2.0)
        assert result == [5, None, 15]
