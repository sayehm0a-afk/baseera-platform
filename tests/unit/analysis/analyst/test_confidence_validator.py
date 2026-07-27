"""Unit tests for ConfidenceValidator -- bands and narrates
InvestmentDecision.confidence, never recomputes it."""

import pytest

from src.analysis.analyst.confidence_validator import ConfidenceValidator
from src.analysis.analyst.types import ConflictAssessment, ConfidenceBand, TensionLevel
from tests.unit.analysis.analyst._fixtures import make_breakdown, make_decision, make_evidence

_NO_CONFLICT = ConflictAssessment(
    has_conflict=False, tension_level=TensionLevel.NONE, conflicting_categories=[], narrative="aligned",
    alternative_scenarios=["none"],
)
_WITH_CONFLICT = ConflictAssessment(
    has_conflict=True, tension_level=TensionLevel.HIGH, conflicting_categories=[("A", "B")],
    narrative="conflict!", alternative_scenarios=["scenario"],
)


@pytest.mark.parametrize(
    "confidence,expected_band",
    [
        (90.0, ConfidenceBand.VERY_HIGH),
        (85.0, ConfidenceBand.VERY_HIGH),
        (70.0, ConfidenceBand.HIGH),
        (65.0, ConfidenceBand.HIGH),
        (50.0, ConfidenceBand.MODERATE),
        (45.0, ConfidenceBand.MODERATE),
        (30.0, ConfidenceBand.LOW),
        (25.0, ConfidenceBand.LOW),
        (10.0, ConfidenceBand.VERY_LOW),
        (0.0, ConfidenceBand.VERY_LOW),
    ],
)
def test_confidence_bands(confidence, expected_band):
    decision = make_decision(confidence=confidence)
    evidence = make_evidence(decision=decision)

    assessment = ConfidenceValidator().validate(evidence, _NO_CONFLICT)

    assert assessment.band is expected_band
    assert assessment.confidence == confidence


def test_never_recomputes_the_confidence_value():
    decision = make_decision(confidence=42.5)
    evidence = make_evidence(decision=decision)
    assessment = ConfidenceValidator().validate(evidence, _NO_CONFLICT)
    assert assessment.confidence == 42.5


def test_narrative_discloses_unavailable_categories():
    breakdown = [
        make_breakdown(category="Technical Analysis", available=True),
        make_breakdown(category="News", available=False),
    ]
    decision = make_decision(breakdown=breakdown)
    evidence = make_evidence(decision=decision, contributor_breakdown=breakdown)

    assessment = ConfidenceValidator().validate(evidence, _NO_CONFLICT)

    assert "News" in assessment.narrative
    assert "missing data" in assessment.narrative


def test_narrative_notes_when_everything_was_available():
    breakdown = [make_breakdown(category="Technical Analysis", available=True)]
    decision = make_decision(breakdown=breakdown)
    evidence = make_evidence(decision=decision, contributor_breakdown=breakdown)

    assessment = ConfidenceValidator().validate(evidence, _NO_CONFLICT)

    assert "Every analysis category had data available" in assessment.narrative


def test_narrative_mentions_conflict_when_present():
    evidence = make_evidence()
    assessment = ConfidenceValidator().validate(evidence, _WITH_CONFLICT)
    assert "disagreement" in assessment.narrative


def test_narrative_mentions_no_disagreement_when_absent():
    evidence = make_evidence()
    assessment = ConfidenceValidator().validate(evidence, _NO_CONFLICT)
    assert "No significant disagreement" in assessment.narrative
