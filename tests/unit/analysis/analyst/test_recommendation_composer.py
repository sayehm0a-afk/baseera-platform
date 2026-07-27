"""Unit tests for RecommendationComposer."""

from src.analysis.analyst.recommendation_composer import RecommendationComposer
from src.analysis.analyst.signal_interpreter import SignalInterpreter
from src.analysis.analyst.types import ConfidenceAssessment, ConflictAssessment, ConfidenceBand, TensionLevel
from src.analysis.recommendation.types import Recommendation, SignalDirection
from tests.unit.analysis.analyst._fixtures import make_decision, make_evidence, make_signal

_NO_CONFLICT = ConflictAssessment(
    has_conflict=False, tension_level=TensionLevel.NONE, conflicting_categories=[], narrative="aligned evidence",
    alternative_scenarios=[],
)
_WITH_CONFLICT = ConflictAssessment(
    has_conflict=True, tension_level=TensionLevel.HIGH, conflicting_categories=[("Technical Analysis", "Risk")],
    narrative="Technical Analysis and Risk disagree.", alternative_scenarios=[],
)
_CONFIDENCE = ConfidenceAssessment(confidence=75.0, band=ConfidenceBand.HIGH, narrative="high confidence")


def test_investment_summary_states_recommendation_and_confidence():
    decision = make_decision(recommendation=Recommendation.BUY, confidence=75.0, final_score=65.0)
    evidence = make_evidence(decision=decision, signals=[], contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)

    rationale = RecommendationComposer().compose(evidence, interpreted, _NO_CONFLICT, _CONFIDENCE)

    assert "Buy" in rationale.summary
    assert "75.0%" in rationale.summary
    assert "65.0/100" in rationale.summary
    assert "broadly aligned" in rationale.summary


def test_investment_summary_flags_conflict():
    decision = make_decision()
    evidence = make_evidence(decision=decision, signals=[], contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)

    rationale = RecommendationComposer().compose(evidence, interpreted, _WITH_CONFLICT, _CONFIDENCE)

    assert "disagreement" in rationale.summary


def test_final_rationale_cites_top_bullish_factor_for_a_bullish_call():
    decision = make_decision(final_score=65.0)
    signals = [
        make_signal(name="strong", source="technical", direction=SignalDirection.BULLISH, impact=20.0),
        make_signal(name="weak", source="momentum", direction=SignalDirection.BULLISH, impact=5.0),
    ]
    evidence = make_evidence(decision=decision, signals=signals, contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)

    rationale = RecommendationComposer().compose(evidence, interpreted, _NO_CONFLICT, _CONFIDENCE)

    assert interpreted.bullish_factors[0].description.rstrip(".") in rationale.final_rationale


def test_final_rationale_cites_top_bearish_factor_for_a_bearish_call():
    decision = make_decision(final_score=35.0)
    signals = [make_signal(name="bad", source="technical", direction=SignalDirection.BEARISH, impact=-18.0)]
    evidence = make_evidence(decision=decision, signals=signals, contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)

    rationale = RecommendationComposer().compose(evidence, interpreted, _NO_CONFLICT, _CONFIDENCE)

    assert interpreted.bearish_factors[0].description.rstrip(".") in rationale.final_rationale


def test_final_rationale_appends_conflict_narrative_when_present():
    decision = make_decision()
    evidence = make_evidence(decision=decision, signals=[], contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)

    rationale = RecommendationComposer().compose(evidence, interpreted, _WITH_CONFLICT, _CONFIDENCE)

    assert "Technical Analysis and Risk disagree." in rationale.final_rationale


def test_final_rationale_has_no_conflict_tail_when_aligned():
    decision = make_decision()
    evidence = make_evidence(decision=decision, signals=[], contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)

    rationale = RecommendationComposer().compose(evidence, interpreted, _NO_CONFLICT, _CONFIDENCE)

    assert "disagree" not in rationale.final_rationale
