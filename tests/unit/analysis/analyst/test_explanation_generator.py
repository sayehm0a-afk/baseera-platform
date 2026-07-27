"""Unit tests for ExplanationGenerator -- pure assembly; every one of
the twelve required Explanation fields must always be populated from
the stage that produced it."""

from src.analysis.analyst.explanation_generator import ExplanationGenerator
from src.analysis.analyst.prompt_templates import PromptTemplateManager
from src.analysis.analyst.recommendation_composer import RecommendationComposer
from src.analysis.analyst.signal_interpreter import SignalInterpreter
from src.analysis.analyst.types import (
    ConfidenceAssessment,
    ConflictAssessment,
    ConfidenceBand,
    RecommendationRationale,
    TensionLevel,
)
from src.analysis.recommendation.types import SignalDirection
from tests.unit.analysis.analyst._fixtures import make_decision, make_evidence, make_signal


def test_generate_assembles_all_twelve_sections():
    decision = make_decision()
    signals = [
        make_signal(name="bull", source="technical", direction=SignalDirection.BULLISH, impact=10.0),
        make_signal(name="bear", source="fundamental", direction=SignalDirection.BEARISH, impact=-8.0),
    ]
    evidence = make_evidence(decision=decision, signals=signals, contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)
    conflict = ConflictAssessment(
        has_conflict=True, tension_level=TensionLevel.MODERATE, conflicting_categories=[("A", "B")],
        narrative="conflict narrative", alternative_scenarios=["scenario one"],
    )
    confidence_assessment = ConfidenceAssessment(confidence=70.0, band=ConfidenceBand.HIGH, narrative="conf narrative")

    rationale = RecommendationComposer(PromptTemplateManager()).compose(evidence, interpreted, conflict, confidence_assessment)

    explanation = ExplanationGenerator().generate(
        evidence,
        interpreted,
        conflict,
        confidence_assessment,
        rationale,
        technical_reasoning="tech text",
        fundamental_reasoning="fund text",
        risk_explanation="risk text",
        target_price_explanation="target text",
        stop_loss_explanation="stop text",
        time_horizon_explanation="horizon text",
    )

    assert explanation.investment_summary == rationale.summary
    assert explanation.technical_reasoning == "tech text"
    assert explanation.fundamental_reasoning == "fund text"
    assert explanation.risk_explanation == "risk text"
    assert explanation.bullish_factors == [f.description for f in interpreted.bullish_factors]
    assert explanation.bearish_factors == [f.description for f in interpreted.bearish_factors]
    assert explanation.confidence_explanation == "conf narrative"
    assert explanation.target_price_explanation == "target text"
    assert explanation.stop_loss_explanation == "stop text"
    assert explanation.time_horizon_explanation == "horizon text"
    assert explanation.alternative_scenarios == ["scenario one"]
    assert explanation.final_recommendation_rationale == rationale.final_rationale


def test_generate_handles_no_bullish_or_bearish_factors():
    evidence = make_evidence(signals=[], contributor_breakdown=[])
    interpreted = SignalInterpreter().interpret(evidence)
    conflict = ConflictAssessment(
        has_conflict=False, tension_level=TensionLevel.NONE, conflicting_categories=[], narrative="",
        alternative_scenarios=[],
    )
    confidence_assessment = ConfidenceAssessment(confidence=50.0, band=ConfidenceBand.MODERATE, narrative="")

    rationale = RecommendationRationale(summary="summary", final_rationale="rationale")

    explanation = ExplanationGenerator().generate(
        evidence, interpreted, conflict, confidence_assessment, rationale,
        technical_reasoning="t", fundamental_reasoning="f", risk_explanation="r",
        target_price_explanation="tp", stop_loss_explanation="sl", time_horizon_explanation="th",
    )

    assert explanation.bullish_factors == []
    assert explanation.bearish_factors == []
