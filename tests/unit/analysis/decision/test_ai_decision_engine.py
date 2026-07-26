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

from src.analysis.decision.ai_decision_engine import AIDecisionEngine
from src.analysis.decision.types import AIDecisionTuning, PositionSize, RiskLevel, TimeHorizon
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.types import (
    AnalysisContext,
    Recommendation,
    ScoreContribution,
    Signal,
    SignalDirection,
)
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import IndicatorCategory, IndicatorOutput, SupportResistanceLevels


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


def _technical_result_with_levels(atr=2.0, support=None, resistance=None):
    return TechnicalAnalysisResult(
        indicators={
            "atr_14": IndicatorOutput(name="atr_14", category=IndicatorCategory.VOLATILITY, value=pd.Series([atr])),
            "adx_14": IndicatorOutput(name="adx_14", category=IndicatorCategory.TREND, value=pd.Series([20.0])),
            "support_resistance": IndicatorOutput(
                name="support_resistance", category=IndicatorCategory.PRICE_ACTION,
                value=SupportResistanceLevels(support=support or [], resistance=resistance or []),
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
