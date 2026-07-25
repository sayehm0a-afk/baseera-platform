"""Unit tests for ConflictResolver."""

from src.analysis.analyst.conflict_resolver import ConflictResolver
from src.analysis.analyst.signal_interpreter import SignalInterpreter
from src.analysis.analyst.types import TensionLevel
from src.analysis.recommendation.types import SignalDirection
from tests.unit.analysis.analyst._fixtures import make_breakdown, make_evidence, make_signal


def _resolve(breakdown, signals=None):
    evidence = make_evidence(signals=signals or [], contributor_breakdown=breakdown)
    interpreted = SignalInterpreter().interpret(evidence)
    return ConflictResolver().resolve(evidence, interpreted), evidence, interpreted


def test_aligned_categories_produce_no_conflict():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=12.0),
        make_breakdown(category="Fundamental Analysis", points=10.0),
    ]
    conflict, _, _ = _resolve(breakdown)
    assert conflict.has_conflict is False
    assert conflict.tension_level is TensionLevel.NONE
    assert conflict.conflicting_categories == []


def test_mild_tension_when_spread_is_small_but_nonzero():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=8.0),
        make_breakdown(category="Fundamental Analysis", points=2.0),
    ]
    conflict, _, _ = _resolve(breakdown)
    assert conflict.tension_level is TensionLevel.MILD


def test_moderate_tension_for_a_medium_spread():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=10.0),
        make_breakdown(category="Fundamental Analysis", points=-10.0),
    ]
    conflict, _, _ = _resolve(breakdown)
    assert conflict.tension_level is TensionLevel.MODERATE


def test_high_tension_for_a_large_spread():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=20.0),
        make_breakdown(category="Fundamental Analysis", points=-15.0),
    ]
    conflict, _, _ = _resolve(breakdown)
    assert conflict.tension_level is TensionLevel.HIGH
    assert conflict.has_conflict is True


def test_tension_is_none_when_either_leg_unavailable():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=20.0, available=True),
        make_breakdown(category="Fundamental Analysis", points=0.0, available=False),
    ]
    conflict, _, _ = _resolve(breakdown)
    assert conflict.tension_level is TensionLevel.NONE


def test_opposing_category_tilts_are_reported_as_conflicting_pairs():
    breakdown = [
        make_breakdown(category="Momentum", points=10.0),
        make_breakdown(category="Volume", points=-10.0),
    ]
    conflict, _, _ = _resolve(breakdown)
    assert ("Momentum", "Volume") in conflict.conflicting_categories
    assert conflict.has_conflict is True


def test_alternative_scenarios_cite_top_bearish_and_bullish_factors_when_conflicted():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=20.0),
        make_breakdown(category="Fundamental Analysis", points=-15.0),
    ]
    signals = [
        make_signal(name="bull", source="technical", direction=SignalDirection.BULLISH, impact=20.0),
        make_signal(name="bear", source="fundamental", direction=SignalDirection.BEARISH, impact=-15.0),
    ]
    conflict, _, _ = _resolve(breakdown, signals=signals)
    assert len(conflict.alternative_scenarios) == 2
    assert any("fundamental analysis" in s.lower() for s in conflict.alternative_scenarios)
    assert any("technical analysis" in s.lower() for s in conflict.alternative_scenarios)


def test_alternative_scenarios_have_a_fallback_when_nothing_conflicts_and_confidence_is_high():
    breakdown = [
        make_breakdown(category="Technical Analysis", points=12.0),
        make_breakdown(category="Fundamental Analysis", points=10.0),
    ]
    evidence = make_evidence(signals=[], contributor_breakdown=breakdown)
    interpreted = SignalInterpreter().interpret(evidence)
    conflict = ConflictResolver().resolve(evidence, interpreted)
    assert len(conflict.alternative_scenarios) == 1
    assert "significant new development" in conflict.alternative_scenarios[0]
