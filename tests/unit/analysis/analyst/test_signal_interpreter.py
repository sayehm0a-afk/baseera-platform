"""Unit tests for SignalInterpreter."""

from src.analysis.analyst.signal_interpreter import SignalInterpreter
from src.analysis.analyst.types import FactorStrength
from src.analysis.recommendation.types import SignalDirection
from tests.unit.analysis.analyst._fixtures import make_breakdown, make_evidence, make_signal


def test_signals_are_grouped_by_direction():
    signals = [
        make_signal(name="s1", direction=SignalDirection.BULLISH, impact=10.0),
        make_signal(name="s2", direction=SignalDirection.BEARISH, impact=-8.0),
        make_signal(name="s3", direction=SignalDirection.NEUTRAL, impact=0.0),
    ]
    evidence = make_evidence(signals=signals, contributor_breakdown=[])

    interpreted = SignalInterpreter().interpret(evidence)

    assert len(interpreted.bullish_factors) == 1
    assert len(interpreted.bearish_factors) == 1
    assert len(interpreted.neutral_factors) == 1


def test_bullish_factors_are_sorted_by_descending_impact():
    signals = [
        make_signal(name="weak", direction=SignalDirection.BULLISH, impact=3.0),
        make_signal(name="strong", direction=SignalDirection.BULLISH, impact=20.0),
        make_signal(name="medium", direction=SignalDirection.BULLISH, impact=7.0),
    ]
    evidence = make_evidence(signals=signals, contributor_breakdown=[])

    interpreted = SignalInterpreter().interpret(evidence)

    assert [f.impact for f in interpreted.bullish_factors] == [20.0, 7.0, 3.0]


def test_strength_thresholds():
    signals = [
        make_signal(name="strong", direction=SignalDirection.BULLISH, impact=15.0),
        make_signal(name="moderate", direction=SignalDirection.BULLISH, impact=7.0),
        make_signal(name="mild", direction=SignalDirection.BULLISH, impact=2.0),
    ]
    evidence = make_evidence(signals=signals, contributor_breakdown=[])

    interpreted = SignalInterpreter().interpret(evidence)
    strengths = {f.impact: f.strength for f in interpreted.bullish_factors}

    assert strengths[15.0] == FactorStrength.STRONG
    assert strengths[7.0] == FactorStrength.MODERATE
    assert strengths[2.0] == FactorStrength.MILD


def test_category_resolved_from_known_source_via_category_labels():
    signals = [make_signal(name="s", source="momentum", direction=SignalDirection.BULLISH, impact=10.0)]
    evidence = make_evidence(signals=signals, contributor_breakdown=[])

    interpreted = SignalInterpreter().interpret(evidence)

    assert interpreted.bullish_factors[0].category == "Momentum"


def test_category_falls_back_to_title_case_for_unknown_source():
    signals = [make_signal(name="s", source="custom_module", direction=SignalDirection.BULLISH, impact=10.0)]
    evidence = make_evidence(signals=signals, contributor_breakdown=[])

    interpreted = SignalInterpreter().interpret(evidence)

    assert interpreted.bullish_factors[0].category == "Custom Module"


def test_category_tilts_reflect_breakdown_points_and_availability():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=15.0, available=True),
        make_breakdown(category="Fundamental Analysis", points=-10.0, available=True),
        make_breakdown(category="Risk", points=0.0, available=True),
        make_breakdown(category="News", points=5.0, available=False),
    ]
    evidence = make_evidence(signals=[], contributor_breakdown=breakdown)

    interpreted = SignalInterpreter().interpret(evidence)

    assert interpreted.category_tilts["Technical Analysis"] == "bullish"
    assert interpreted.category_tilts["Fundamental Analysis"] == "bearish"
    assert interpreted.category_tilts["Risk"] == "neutral"
    assert interpreted.category_tilts["News"] == "unavailable"
