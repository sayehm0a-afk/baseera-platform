"""Unit tests for AIDecisionEngine.

Uses small fake ScoreContributors (the same technique
test_recommendation_engine.py uses) so the decision-layer-specific
logic -- target price/stop loss, risk level, time horizon, position
size, reasons, breakdown -- can be tested in complete isolation from
the real Momentum/Volume/Risk/News/Macro scoring rules, which are
covered by their own test files.
"""

import pandas as pd
import pytest

from src.analysis.decision.ai_decision_engine import (
    AIDecisionEngine,
    _calibrate_confidence,
    _derive_entry_quality,
    _derive_position_size,
    _derive_time_horizon,
)
from src.analysis.decision.types import AIDecisionTuning, EntryQuality, PositionSize, RiskLevel, TimeHorizon
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.types import (
    AnalysisContext,
    Recommendation,
    ScoreContribution,
    Signal,
    SignalDirection,
)
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import (
    FibonacciLevels,
    IndicatorCategory,
    IndicatorOutput,
    SupportResistanceLevels,
    VolumeProfileResult,
)


class _FakeContributor:
    def __init__(self, name, score, weight=1.0, confidence=100.0, signals=None, notes=None):
        self.name = name
        self.default_weight = weight
        self._score = score
        self._confidence = confidence
        self._signals = signals or []
        self._notes = notes

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        return ScoreContribution(
            source=self.name,
            score=self._score,
            weight=self.default_weight if self._score is not None else 0.0,
            confidence=self._confidence,
            signals=self._signals,
            notes=self._notes,
        )


def _engine(contributors):
    return AIDecisionEngine(recommendation_engine=RecommendationEngine(contributors=contributors))


def _context(latest_price=None, technical_result=None):
    return AnalysisContext(symbol="2222", latest_price=latest_price, technical_result=technical_result)


def _technical_result_with_levels(
    atr=2.0, support=None, resistance=None, vwap=100.0, fib_levels=None, is_uptrend=True, adx=20.0,
    bin_edges=None, bin_volumes=None, point_of_control=100.0,
):
    return TechnicalAnalysisResult(
        indicators={
            "atr_14": IndicatorOutput(name="atr_14", category=IndicatorCategory.VOLATILITY, value=pd.Series([atr])),
            "adx_14": IndicatorOutput(name="adx_14", category=IndicatorCategory.TREND, value=pd.Series([adx])),
            "support_resistance": IndicatorOutput(
                name="support_resistance", category=IndicatorCategory.PRICE_ACTION,
                value=SupportResistanceLevels(support=support or [], resistance=resistance or []),
            ),
            "fibonacci_retracement": IndicatorOutput(
                name="fibonacci_retracement", category=IndicatorCategory.PRICE_ACTION,
                value=FibonacciLevels(
                    swing_high=110.0, swing_high_at=1, swing_low=90.0, swing_low_at=0,
                    is_uptrend=is_uptrend, levels=fib_levels or {},
                ),
            ),
            "vwap_20": IndicatorOutput(name="vwap_20", category=IndicatorCategory.VOLUME, value=pd.Series([vwap])),
            "volume_profile": IndicatorOutput(
                name="volume_profile", category=IndicatorCategory.VOLUME,
                value=VolumeProfileResult(
                    bin_edges=bin_edges or [95.0, 100.0, 105.0],
                    bin_volumes=bin_volumes or [100.0, 100.0],
                    point_of_control=point_of_control,
                ),
            ),
        }
    )


# --- basic wiring: reuses RecommendationEngine's output verbatim -----------


def test_decision_reuses_recommendation_engines_score_and_confidence():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0, confidence=90.0)])
    decision = engine.decide(_context())
    assert decision.final_score == 80.0
    assert decision.recommendation == Recommendation.STRONG_BUY


def test_requesting_user_id_is_accepted_and_has_no_effect_on_the_result():
    # Phase 10 M10.8: accepted for API-consistency with AnalystEngine/
    # RecommendationEngine -- this engine makes no LLM call, so passing
    # it must be a pure no-op.
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0, confidence=90.0)])
    decision = engine.decide(_context(), requesting_user_id=42)
    assert decision.final_score == 80.0
    assert decision.confidence == 90.0


def test_default_construction_uses_all_eleven_contributors():
    engine = AIDecisionEngine()
    decision = engine.decide(AnalysisContext(symbol="2222"))
    sources = {b.category for b in decision.breakdown}
    assert sources == {
        "Technical Analysis", "Fundamental Analysis", "Momentum", "Volume", "Risk",
        "Price Structure", "Value Area",
        "News", "Macro", "Insider Transactions", "Sector Rotation",
    }


# --- target price / stop loss / expected return ---------------------------


def test_no_price_available_means_no_targets():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=None))
    assert decision.target_price is None
    assert decision.stop_loss is None
    assert decision.expected_return_pct is None


def test_bullish_decision_targets_above_price_and_stops_below():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0))
    assert decision.target_price > 100.0
    assert decision.stop_loss < 100.0
    assert decision.expected_return_pct > 0


def test_bearish_decision_targets_below_price_and_stops_above():
    engine = _engine([_FakeContributor("technical", score=20.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0))
    assert decision.target_price < 100.0
    assert decision.stop_loss > 100.0
    assert decision.expected_return_pct < 0


def test_higher_conviction_widens_the_reward_distance():
    weak = _engine([_FakeContributor("technical", score=65.0, weight=1.0)]).decide(_context(latest_price=100.0))
    strong = _engine([_FakeContributor("technical", score=95.0, weight=1.0)]).decide(_context(latest_price=100.0))
    assert (strong.target_price - 100.0) > (weak.target_price - 100.0)


# --- price targets refined by real support/resistance levels ---------------


def test_bullish_target_is_capped_just_below_a_resistance_level_inside_the_atr_range():
    # Default tuning at score=80 (conviction 0.6) with ATR=2 on price=100
    # would target well above 106 -- a resistance at 103 sits inside that
    # range and must cap the target, not the raw ATR projection.
    technical_result = _technical_result_with_levels(atr=2.0, resistance=[103.0])
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))

    assert decision.target_price < 103.0
    assert decision.target_price > 100.0
    assert any("resistance" in r for r in decision.reasons)


def test_bullish_stop_is_tightened_to_just_below_a_support_level_inside_the_atr_range():
    technical_result = _technical_result_with_levels(atr=2.0, support=[98.5])
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))

    assert decision.stop_loss > 97.0  # tighter than the raw ATR-only stop would be
    assert decision.stop_loss < 100.0
    assert any("support" in r for r in decision.reasons)


def test_bearish_target_is_capped_just_above_a_support_level_inside_the_atr_range():
    technical_result = _technical_result_with_levels(atr=2.0, support=[97.0])
    engine = _engine([_FakeContributor("technical", score=20.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))

    assert decision.target_price > 97.0
    assert decision.target_price < 100.0


def test_bearish_stop_is_tightened_to_just_above_a_resistance_level_inside_the_atr_range():
    technical_result = _technical_result_with_levels(atr=2.0, resistance=[101.5])
    engine = _engine([_FakeContributor("technical", score=20.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))

    assert decision.stop_loss < 103.0  # tighter than the raw ATR-only stop would be
    assert decision.stop_loss > 100.0


def test_bullish_target_never_drops_below_price_when_resistance_sits_within_the_buffer():
    # Reproduces the 2026-07-30 live scan defect (symbol 1020/BJAZ): a
    # resistance level 0.3% above price fell inside the ATR range, and
    # the old refinement unconditionally capped the target to
    # nearest*(1 - _LEVEL_BUFFER_PCT) -- for a level this close to
    # price, that buffered value landed *below* price itself, so a BUY
    # recommendation carried a negative expected return and still got
    # ranked TOP_BUY by score. A level too close to leave room for the
    # buffer must be skipped, not used as the target basis.
    technical_result = _technical_result_with_levels(atr=2.0, resistance=[100.3])
    engine = _engine([_FakeContributor("technical", score=100.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))

    assert decision.target_price > 100.0
    assert decision.expected_return_pct > 0
    assert decision.target_price_basis == "atr"


def test_bearish_target_never_rises_above_price_when_support_sits_within_the_buffer():
    # Mirror of the bullish case above: a support level just below
    # price must not be used to cap a SELL's target above price.
    technical_result = _technical_result_with_levels(atr=2.0, support=[99.7])
    engine = _engine([_FakeContributor("technical", score=0.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))

    assert decision.target_price < 100.0
    assert decision.expected_return_pct < 0
    assert decision.target_price_basis == "atr"


def test_no_level_inside_the_atr_range_leaves_targets_unrefined():
    technical_result = _technical_result_with_levels(atr=2.0, resistance=[500.0], support=[1.0])
    with_levels = _engine([_FakeContributor("technical", score=80.0, weight=1.0)]).decide(
        _context(latest_price=100.0, technical_result=technical_result)
    )
    without_levels = _engine([_FakeContributor("technical", score=80.0, weight=1.0)]).decide(
        _context(latest_price=100.0)
    )
    assert with_levels.target_price == without_levels.target_price
    assert with_levels.stop_loss == without_levels.stop_loss


# --- risk level --------------------------------------------------------


def test_risk_level_defaults_to_medium_when_risk_contributor_absent():
    engine = _engine([_FakeContributor("technical", score=70.0, weight=1.0)])
    decision = engine.decide(_context())
    assert decision.risk_level == RiskLevel.MEDIUM


@pytest.mark.parametrize(
    "risk_score,expected",
    [
        (90.0, RiskLevel.LOW),
        (65.0, RiskLevel.LOW),
        (50.0, RiskLevel.MEDIUM),
        (45.0, RiskLevel.MEDIUM),
        (30.0, RiskLevel.HIGH),
        (25.0, RiskLevel.HIGH),
        (10.0, RiskLevel.VERY_HIGH),
    ],
)
def test_risk_level_thresholds(risk_score, expected):
    engine = _engine(
        [
            _FakeContributor("technical", score=60.0, weight=0.8),
            _FakeContributor("risk", score=risk_score, weight=0.2),
        ]
    )
    decision = engine.decide(_context())
    assert decision.risk_level == expected


# --- position sizing ------------------------------------------------------


def test_hold_recommendation_gets_no_position():
    engine = _engine([_FakeContributor("technical", score=50.0, weight=1.0)])
    decision = engine.decide(_context())
    assert decision.recommendation == Recommendation.HOLD
    assert decision.position_size == PositionSize.NONE


def test_strong_buy_with_high_confidence_and_low_risk_gets_large_position():
    engine = _engine(
        [
            _FakeContributor("technical", score=90.0, weight=0.8, confidence=95.0),
            _FakeContributor("risk", score=80.0, weight=0.2, confidence=95.0),
        ]
    )
    decision = engine.decide(_context())
    assert decision.recommendation == Recommendation.STRONG_BUY
    assert decision.position_size == PositionSize.LARGE


def test_high_risk_downgrades_position_size():
    engine = _engine(
        [
            _FakeContributor("technical", score=95.0, weight=0.8, confidence=95.0),
            _FakeContributor("risk", score=10.0, weight=0.2, confidence=95.0),
        ]
    )
    decision = engine.decide(_context())
    assert decision.recommendation == Recommendation.STRONG_BUY
    assert decision.position_size in (PositionSize.SMALL, PositionSize.MODERATE)


# --- time horizon ------------------------------------------------------


def test_weak_conviction_is_short_term():
    engine = _engine([_FakeContributor("technical", score=55.0, weight=1.0)])
    decision = engine.decide(_context())
    assert decision.time_horizon == TimeHorizon.SHORT_TERM


def test_moderate_conviction_is_medium_term():
    engine = _engine([_FakeContributor("technical", score=65.0, weight=1.0)])
    decision = engine.decide(_context())
    assert decision.time_horizon == TimeHorizon.MEDIUM_TERM


# --- breakdown ---------------------------------------------------------


def test_breakdown_points_are_centered_on_zero():
    engine = _engine([_FakeContributor("technical", score=85.0, weight=1.0)])
    decision = engine.decide(_context())
    breakdown = next(b for b in decision.breakdown if b.category == "Technical Analysis")
    assert breakdown.points == 35.0  # 85 - 50


def test_unavailable_contributor_has_zero_points_and_is_flagged():
    engine = _engine(
        [
            _FakeContributor("technical", score=70.0, weight=1.0),
            _FakeContributor("news_sentiment", score=None, weight=0.0, confidence=0.0, notes="no data"),
        ]
    )
    decision = engine.decide(_context())
    breakdown = next(b for b in decision.breakdown if b.category == "News")
    assert breakdown.points == 0.0
    assert breakdown.available is False
    assert breakdown.notes == "no data"


# --- reasons -----------------------------------------------------------


def test_reasons_include_headline_and_top_signals():
    signal = Signal(name="a", description="Big bullish signal", direction=SignalDirection.BULLISH, source="technical", impact=20.0)
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0, signals=[signal])])
    decision = engine.decide(_context())
    assert any("2222" in r for r in decision.reasons)
    assert any("Big bullish signal" in r for r in decision.reasons)
    assert any("Risk assessed as" in r for r in decision.reasons)


def test_reasons_list_unavailable_modules():
    engine = _engine(
        [
            _FakeContributor("technical", score=70.0, weight=1.0),
            _FakeContributor("news_sentiment", score=None, weight=0.0, confidence=0.0, notes="no data"),
        ]
    )
    decision = engine.decide(_context())
    assert any("news_sentiment" in r for r in decision.reasons)


# --- signals passthrough ----------------------------------------------


def test_signals_are_the_same_flattened_list_recommendation_engine_produced():
    signal = Signal(name="a", description="a", direction=SignalDirection.BULLISH, source="technical", impact=5.0)
    engine = _engine([_FakeContributor("technical", score=60.0, weight=1.0, signals=[signal])])
    decision = engine.decide(_context())
    assert signal in decision.signals


# --- tuning (calibration extension point) ---------------------------


def test_default_tuning_matches_prior_hardcoded_behavior():
    engine = AIDecisionEngine(recommendation_engine=RecommendationEngine(contributors=[_FakeContributor("technical", score=80.0, weight=1.0)]))
    decision = engine.decide(_context(latest_price=100.0))
    assert decision.target_price > 100.0
    assert decision.stop_loss < 100.0


def test_custom_atr_multiples_widen_stop_and_target():
    default_engine = AIDecisionEngine(
        recommendation_engine=RecommendationEngine(contributors=[_FakeContributor("technical", score=80.0, weight=1.0)])
    )
    default_decision = default_engine.decide(_context(latest_price=100.0))

    wide_tuning = AIDecisionTuning(stop_atr_multiple=5.0, base_reward_atr_multiple=8.0, max_extra_reward_atr_multiple=0.0)
    wide_engine = AIDecisionEngine(
        recommendation_engine=RecommendationEngine(contributors=[_FakeContributor("technical", score=80.0, weight=1.0)]),
        tuning=wide_tuning,
    )
    wide_decision = wide_engine.decide(_context(latest_price=100.0))

    assert (100.0 - wide_decision.stop_loss) > (100.0 - default_decision.stop_loss)
    assert (wide_decision.target_price - 100.0) > (default_decision.target_price - 100.0)


def test_custom_risk_thresholds_change_risk_level():
    tuning = AIDecisionTuning(risk_low_threshold=10.0)  # almost anything now counts as LOW risk
    engine = AIDecisionEngine(
        recommendation_engine=RecommendationEngine(
            contributors=[
                _FakeContributor("technical", score=60.0, weight=0.8),
                _FakeContributor("risk", score=15.0, weight=0.2),
            ]
        ),
        tuning=tuning,
    )
    decision = engine.decide(_context())
    assert decision.risk_level == RiskLevel.LOW  # would be VERY_HIGH under default thresholds


def test_omitting_tuning_uses_default_ai_decision_tuning():
    engine = AIDecisionEngine(
        recommendation_engine=RecommendationEngine(
            contributors=[
                _FakeContributor("technical", score=60.0, weight=0.8),
                _FakeContributor("risk", score=70.0, weight=0.2),
            ]
        )
    )
    decision = engine.decide(_context())
    assert decision.risk_level == RiskLevel.LOW  # default risk_low_threshold=65.0


# --- entry quality (Phase 11) -----------------------------------------

_TUNING = AIDecisionTuning()


def test_entry_quality_fair_with_no_price():
    quality, notes = _derive_entry_quality(1, None, None, None, None, None, _TUNING)
    assert quality == EntryQuality.FAIR
    assert notes == []


def test_entry_quality_fair_with_no_direction():
    quality, notes = _derive_entry_quality(0, 100.0, None, None, None, None, _TUNING)
    assert quality == EntryQuality.FAIR
    assert notes == []


def test_entry_quality_fair_when_no_structural_data_available():
    quality, notes = _derive_entry_quality(1, 100.0, None, None, None, None, _TUNING)
    assert quality == EntryQuality.FAIR
    assert notes == []


def test_entry_quality_bullish_near_support_is_good():
    sr = SupportResistanceLevels(support=[99.5], resistance=[])
    quality, notes = _derive_entry_quality(1, 100.0, sr, None, None, None, _TUNING)
    assert quality == EntryQuality.GOOD
    assert any("favorable, defensible entry" in n for n in notes)


def test_entry_quality_bullish_near_resistance_is_poor():
    sr = SupportResistanceLevels(support=[], resistance=[100.5])
    quality, notes = _derive_entry_quality(1, 100.0, sr, None, None, None, _TUNING)
    assert quality == EntryQuality.POOR
    assert any("poor entry" in n for n in notes)


def test_entry_quality_bearish_near_resistance_is_good():
    sr = SupportResistanceLevels(support=[], resistance=[100.5])
    quality, notes = _derive_entry_quality(-1, 100.0, sr, None, None, None, _TUNING)
    assert quality == EntryQuality.GOOD
    assert any("favorable, defensible entry" in n for n in notes)


def test_entry_quality_bearish_near_support_is_poor():
    sr = SupportResistanceLevels(support=[99.5], resistance=[])
    quality, notes = _derive_entry_quality(-1, 100.0, sr, None, None, None, _TUNING)
    assert quality == EntryQuality.POOR
    assert any("poor entry" in n for n in notes)


def test_entry_quality_fibonacci_favorable_bullish_uptrend_is_good():
    fib = FibonacciLevels(
        swing_high=110.0, swing_high_at=1, swing_low=90.0, swing_low_at=0, is_uptrend=True, levels={"61.8": 99.7}
    )
    quality, notes = _derive_entry_quality(1, 100.0, None, fib, None, None, _TUNING)
    assert quality == EntryQuality.GOOD
    assert any("good timing" in n for n in notes)


def test_entry_quality_fibonacci_unfavorable_bullish_downtrend_is_weaker():
    fib = FibonacciLevels(
        swing_high=110.0, swing_high_at=1, swing_low=90.0, swing_low_at=0, is_uptrend=False, levels={"61.8": 99.7}
    )
    quality, notes = _derive_entry_quality(1, 100.0, None, fib, None, None, _TUNING)
    assert quality == EntryQuality.FAIR
    assert any("weaker timing" in n for n in notes)


def test_entry_quality_vwap_extended_bullish_is_penalized():
    quality, notes = _derive_entry_quality(1, 100.0, None, None, 97.0, None, _TUNING)
    assert quality == EntryQuality.FAIR
    assert any("extended" in n for n in notes)


def test_entry_quality_vwap_fair_value_boosts_quality():
    quality, notes = _derive_entry_quality(1, 100.0, None, None, 100.5, None, _TUNING)
    assert quality == EntryQuality.GOOD
    assert any("fair-value entry" in n for n in notes)


def test_entry_quality_near_point_of_control_boosts_quality():
    vp = VolumeProfileResult(bin_edges=[95.0, 100.0, 105.0], bin_volumes=[100.0, 100.0], point_of_control=100.5)
    quality, notes = _derive_entry_quality(1, 100.0, None, None, None, vp, _TUNING)
    assert quality == EntryQuality.GOOD
    assert any("point of control" in n for n in notes)


def test_entry_quality_excellent_when_multiple_factors_align():
    sr = SupportResistanceLevels(support=[99.5], resistance=[])
    fib = FibonacciLevels(
        swing_high=110.0, swing_high_at=1, swing_low=90.0, swing_low_at=0, is_uptrend=True, levels={"61.8": 99.6}
    )
    quality, notes = _derive_entry_quality(1, 100.0, sr, fib, None, None, _TUNING)
    assert quality == EntryQuality.EXCELLENT
    assert len(notes) == 2


# --- time horizon key-level override (Phase 11) ------------------------


def test_time_horizon_key_level_proximity_forces_short_term_despite_high_conviction():
    technical_result = _technical_result_with_levels(support=[99.5], adx=30.0)
    horizon = _derive_time_horizon(90.0, technical_result, 100.0, _TUNING)
    assert horizon == TimeHorizon.SHORT_TERM


def test_time_horizon_long_term_when_no_key_level_nearby():
    technical_result = _technical_result_with_levels(support=[1.0], resistance=[500.0], adx=30.0)
    horizon = _derive_time_horizon(90.0, technical_result, 100.0, _TUNING)
    assert horizon == TimeHorizon.LONG_TERM


def test_time_horizon_key_level_override_skipped_without_price():
    technical_result = _technical_result_with_levels(support=[99.5], adx=30.0)
    horizon = _derive_time_horizon(90.0, technical_result, None, _TUNING)
    assert horizon == TimeHorizon.LONG_TERM


# --- confidence calibration (Phase 11) ----------------------------------


def test_calibrate_confidence_no_change_without_price_or_direction():
    confidence, notes = _calibrate_confidence(70.0, 0, 100.0, 100.0, None, _TUNING)
    assert confidence == 70.0
    assert notes == []


def test_calibrate_confidence_no_notes_when_no_vwap_or_volume_profile():
    confidence, notes = _calibrate_confidence(70.0, 1, 100.0, None, None, _TUNING)
    assert confidence == 70.0
    assert notes == []


def test_calibrate_confidence_vwap_aligned_boosts():
    confidence, notes = _calibrate_confidence(70.0, 1, 101.0, 100.0, None, _TUNING)
    assert confidence == 73.0
    assert any("intraday confidence boosted" in n for n in notes)


def test_calibrate_confidence_vwap_misaligned_reduces():
    confidence, notes = _calibrate_confidence(70.0, 1, 99.0, 100.0, None, _TUNING)
    assert confidence == 67.0
    assert any("intraday confidence reduced" in n for n in notes)


def test_calibrate_confidence_thin_liquidity_zone_reduces():
    vp = VolumeProfileResult(bin_edges=[95.0, 100.0, 105.0], bin_volumes=[10.0, 100.0], point_of_control=100.0)
    confidence, notes = _calibrate_confidence(70.0, 1, 97.0, None, vp, _TUNING)
    assert confidence == 67.0
    assert any("liquidity confidence reduced" in n for n in notes)


def test_calibrate_confidence_thick_liquidity_zone_boosts():
    vp = VolumeProfileResult(bin_edges=[95.0, 100.0, 105.0], bin_volumes=[10.0, 100.0], point_of_control=100.0)
    confidence, notes = _calibrate_confidence(70.0, 1, 103.0, None, vp, _TUNING)
    assert confidence == 73.0
    assert any("liquidity confidence boosted" in n for n in notes)


def test_calibrate_confidence_combines_vwap_and_liquidity():
    vp = VolumeProfileResult(bin_edges=[95.0, 100.0, 105.0], bin_volumes=[10.0, 100.0], point_of_control=100.0)
    confidence, notes = _calibrate_confidence(70.0, 1, 103.0, 100.0, vp, _TUNING)
    assert confidence == 76.0
    assert len(notes) == 2


def test_calibrate_confidence_clamped_at_100():
    vp = VolumeProfileResult(bin_edges=[95.0, 100.0, 105.0], bin_volumes=[10.0, 100.0], point_of_control=100.0)
    confidence, _notes = _calibrate_confidence(99.0, 1, 103.0, 100.0, vp, _TUNING)
    assert confidence == 100.0


def test_calibrate_confidence_clamped_at_0():
    confidence, _notes = _calibrate_confidence(1.0, 1, 99.0, 100.0, None, _TUNING)
    assert confidence == 0.0


# --- position size: entry quality / risk-reward (Phase 11) -------------


def test_position_size_poor_entry_quality_downgrades():
    size = _derive_position_size(Recommendation.BUY, 80.0, RiskLevel.LOW, EntryQuality.POOR, 1.5, _TUNING)
    assert size == PositionSize.MODERATE


def test_position_size_weak_risk_reward_downgrades():
    size = _derive_position_size(Recommendation.BUY, 80.0, RiskLevel.LOW, EntryQuality.FAIR, 0.5, _TUNING)
    assert size == PositionSize.MODERATE


def test_position_size_excellent_entry_and_strong_reward_upgrades():
    size = _derive_position_size(Recommendation.BUY, 80.0, RiskLevel.LOW, EntryQuality.EXCELLENT, 2.5, _TUNING)
    assert size == PositionSize.LARGE


def test_position_size_no_risk_reward_data_has_no_effect():
    size = _derive_position_size(Recommendation.BUY, 80.0, RiskLevel.LOW, EntryQuality.FAIR, None, _TUNING)
    assert size == PositionSize.STANDARD


def test_position_size_poor_entry_and_weak_reward_combine_downgrades():
    size = _derive_position_size(Recommendation.STRONG_BUY, 80.0, RiskLevel.LOW, EntryQuality.POOR, 0.5, _TUNING)
    assert size == PositionSize.MODERATE


def test_position_size_hold_stays_none_even_with_excellent_entry_and_strong_reward():
    # Regression test: a HOLD must never receive a position size, even
    # when entry_quality/risk_reward_ratio would otherwise earn the
    # EXCELLENT-entry upgrade -- HOLD means "no new position warranted."
    size = _derive_position_size(Recommendation.HOLD, 90.0, RiskLevel.LOW, EntryQuality.EXCELLENT, 5.0, _TUNING)
    assert size == PositionSize.NONE


# --- end-to-end Phase 11 fields via decide() ----------------------------


def test_decide_populates_risk_reward_ratio():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0))
    assert decision.risk_reward_ratio is not None
    assert decision.risk_reward_ratio > 0


def test_decide_risk_reward_ratio_none_without_price():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=None))
    assert decision.risk_reward_ratio is None


def test_decide_target_price_basis_reflects_resistance_refinement():
    technical_result = _technical_result_with_levels(atr=2.0, resistance=[103.0])
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))
    assert decision.target_price_basis == "resistance_level"


def test_decide_stop_loss_basis_reflects_support_refinement():
    technical_result = _technical_result_with_levels(atr=2.0, support=[98.5])
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))
    assert decision.stop_loss_basis == "support_level"


def test_decide_basis_defaults_to_atr_without_levels():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0))
    assert decision.target_price_basis == "atr"
    assert decision.stop_loss_basis == "atr"


def test_decide_entry_quality_notes_populate_when_near_support():
    technical_result = _technical_result_with_levels(atr=2.0, support=[99.5])
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))
    assert decision.entry_quality_notes


def test_decide_confidence_calibration_notes_populate_when_vwap_present():
    technical_result = _technical_result_with_levels(atr=2.0, vwap=99.0)
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0, technical_result=technical_result))
    assert decision.confidence_calibration_notes


def test_decide_reasons_include_risk_reward_ratio_line():
    engine = _engine([_FakeContributor("technical", score=80.0, weight=1.0)])
    decision = engine.decide(_context(latest_price=100.0))
    assert any("Risk/reward ratio" in r for r in decision.reasons)
