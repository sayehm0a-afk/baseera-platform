"""Unit tests for RecommendationEngine.

Uses small fake ScoreContributors (not TechnicalScoreContributor/
FundamentalScoreContributor) so the engine's own blending, confidence,
recommendation-threshold, explanation, and pluggability logic can be
tested in complete isolation from either real module's scoring rules
-- those are covered by test_technical_contributor.py and
test_fundamental_contributor.py.
"""

from typing import List, Optional

import pytest

from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.types import (
    AnalysisContext,
    Recommendation,
    ScoreContribution,
    Signal,
    SignalDirection,
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


def _context():
    return AnalysisContext(symbol="2222")


# --- basic blending --------------------------------------------------------


def test_single_contributor_final_score_equals_its_score():
    engine = RecommendationEngine(contributors=[_FakeContributor("technical", score=80.0)])
    result = engine.generate(_context())
    assert result.final_score == 80.0
    assert result.technical_score == 80.0
    assert result.fundamental_score is None


def test_two_equally_weighted_contributors_average():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=80.0, weight=0.5),
            _FakeContributor("fundamental", score=40.0, weight=0.5),
        ]
    )
    result = engine.generate(_context())
    assert result.final_score == 60.0


def test_unequal_weights_are_respected():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=100.0, weight=0.8),
            _FakeContributor("fundamental", score=0.0, weight=0.2),
        ]
    )
    result = engine.generate(_context())
    assert result.final_score == 80.0


def test_no_contributors_available_defaults_to_neutral_hold():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=None, weight=0.5, confidence=0.0, notes="unavailable"),
            _FakeContributor("fundamental", score=None, weight=0.5, confidence=0.0, notes="unavailable"),
        ]
    )
    result = engine.generate(_context())
    assert result.final_score == 50.0
    assert result.confidence == 0.0
    assert result.recommendation == Recommendation.HOLD
    assert result.technical_score is None
    assert result.fundamental_score is None
    assert result.signals == []


# --- confidence: coverage ---------------------------------------------------


def test_partial_coverage_lowers_confidence_versus_full_coverage():
    full = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=70.0, weight=0.5, confidence=90.0),
            _FakeContributor("fundamental", score=70.0, weight=0.5, confidence=90.0),
        ]
    ).generate(_context())

    partial = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=70.0, weight=0.5, confidence=90.0),
            _FakeContributor("fundamental", score=None, weight=0.5, confidence=0.0, notes="unavailable"),
        ]
    ).generate(_context())

    assert partial.confidence < full.confidence


# --- confidence: agreement vs disagreement --------------------------------


def test_agreeing_contributors_get_a_confidence_bonus():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=70.0, weight=0.5, confidence=80.0),
            _FakeContributor("fundamental", score=75.0, weight=0.5, confidence=80.0),
        ]
    )
    result = engine.generate(_context())
    # base weighted confidence would be 80.0; agreement (spread=5) adds a bonus.
    assert result.confidence > 80.0


def test_disagreeing_contributors_get_a_confidence_penalty():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=90.0, weight=0.5, confidence=80.0),
            _FakeContributor("fundamental", score=10.0, weight=0.5, confidence=80.0),
        ]
    )
    result = engine.generate(_context())
    assert result.confidence < 80.0


# --- recommendation thresholds ---------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (100.0, Recommendation.STRONG_BUY),
        (75.0, Recommendation.STRONG_BUY),
        (74.9, Recommendation.BUY),
        (60.0, Recommendation.BUY),
        (59.9, Recommendation.HOLD),
        (40.1, Recommendation.HOLD),
        (40.0, Recommendation.SELL),
        (25.1, Recommendation.SELL),
        (25.0, Recommendation.STRONG_SELL),
        (0.0, Recommendation.STRONG_SELL),
    ],
)
def test_score_to_recommendation_thresholds(score, expected):
    engine = RecommendationEngine(contributors=[_FakeContributor("technical", score=score, weight=1.0)])
    result = engine.generate(_context())
    assert result.recommendation == expected


# --- explanation -------------------------------------------------------


def test_explanation_mentions_recommendation_and_scores():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=80.0, weight=0.5),
            _FakeContributor("fundamental", score=80.0, weight=0.5),
        ]
    )
    result = engine.generate(_context())
    assert "2222" in result.explanation
    assert "Buy" in result.explanation or "BUY" in result.explanation.upper()
    assert "technical" in result.explanation
    assert "fundamental" in result.explanation


def test_explanation_lists_unavailable_modules():
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=70.0, weight=0.5),
            _FakeContributor("fundamental", score=None, weight=0.5, confidence=0.0, notes="unavailable"),
        ]
    )
    result = engine.generate(_context())
    assert "No fundamental data was available" in result.explanation


def test_explanation_surfaces_highest_impact_signals_only():
    signals = [
        Signal(name="a", description="small bullish", direction=SignalDirection.BULLISH, source="technical", impact=1.0),
        Signal(name="b", description="big bullish", direction=SignalDirection.BULLISH, source="technical", impact=20.0),
        Signal(name="c", description="zero impact", direction=SignalDirection.NEUTRAL, source="technical", impact=0.0),
    ]
    engine = RecommendationEngine(contributors=[_FakeContributor("technical", score=70.0, weight=1.0, signals=signals)])
    result = engine.generate(_context())
    assert "big bullish" in result.explanation
    assert "zero impact" not in result.explanation


def test_explanation_caps_the_number_of_signals_listed():
    signals = [
        Signal(name=f"s{i}", description=f"signal {i}", direction=SignalDirection.BULLISH, source="technical", impact=float(i + 1))
        for i in range(10)
    ]
    engine = RecommendationEngine(contributors=[_FakeContributor("technical", score=70.0, weight=1.0, signals=signals)])
    result = engine.generate(_context())
    # only the top 5 highest-impact signals (signal 9 down to signal 5) should appear
    for i in range(5, 10):
        assert f"signal {i}" in result.explanation
    for i in range(0, 5):
        assert f"signal {i}" not in result.explanation


# --- signals aggregation ----------------------------------------------


def test_signals_are_flattened_across_all_contributors():
    tech_signal = Signal(name="t", description="t", direction=SignalDirection.BULLISH, source="technical", impact=5.0)
    fund_signal = Signal(name="f", description="f", direction=SignalDirection.BEARISH, source="fundamental", impact=-5.0)
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=60.0, weight=0.5, signals=[tech_signal]),
            _FakeContributor("fundamental", score=40.0, weight=0.5, signals=[fund_signal]),
        ]
    )
    result = engine.generate(_context())
    assert tech_signal in result.signals
    assert fund_signal in result.signals


def test_contributions_are_exposed_verbatim():
    engine = RecommendationEngine(contributors=[_FakeContributor("technical", score=60.0, weight=1.0)])
    result = engine.generate(_context())
    assert len(result.contributions) == 1
    assert result.contributions[0].source == "technical"


# --- pluggability: a third, future-style module ----------------------------


def test_a_third_contributor_plugs_in_without_engine_changes():
    """Simulates adding a future module (news sentiment, insider
    trades, macro, AI reasoning) alongside the two default modules --
    RecommendationEngine.generate()'s signature and behavior need no
    change; the new module just shows up in contributions/signals."""
    engine = RecommendationEngine(
        contributors=[
            _FakeContributor("technical", score=60.0, weight=1 / 3),
            _FakeContributor("fundamental", score=60.0, weight=1 / 3),
            _FakeContributor("news_sentiment", score=60.0, weight=1 / 3),
        ]
    )
    result = engine.generate(_context())
    assert result.final_score == pytest.approx(60.0)
    sources = {c.source for c in result.contributions}
    assert sources == {"technical", "fundamental", "news_sentiment"}


# --- default construction ---------------------------------------------


def test_default_construction_uses_the_two_m2_contributors():
    engine = RecommendationEngine()
    result = engine.generate(AnalysisContext(symbol="2222"))
    sources = {c.source for c in result.contributions}
    assert sources == {"technical", "fundamental"}
    # neither engine result was supplied -> both unavailable -> neutral HOLD
    assert result.recommendation == Recommendation.HOLD
    assert result.confidence == 0.0
