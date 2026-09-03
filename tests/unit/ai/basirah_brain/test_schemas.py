"""Structural validation tests for BasirahBrainDecisionV1 -- items #1, 9,
10, 11 of the Stage 1 test list (valid output, target ordering,
confidence bounds, no NaN/infinite values)."""

import math

import pytest
from pydantic import ValidationError

from src.ai.basirah_brain.schemas import (
    AgreementStatus,
    BasirahBrainDecisionV1,
    BrainDataQualityOut,
    BrainDecision,
    BrainRiskLevel,
    ConfidenceLabel,
)

_BASE_KWARGS = dict(
    decision=BrainDecision.NO_TRADE,
    confidence_label=ConfidenceLabel.LOW,
    risk_level=BrainRiskLevel.MEDIUM,
    thesis_summary="test",
    data_quality=BrainDataQualityOut(sufficient=True),
    agreement_with_deterministic_engine=AgreementStatus.AGREE,
    deterministic_decision="REJECT",
    brain_decision="NO_TRADE",
)


def test_valid_structured_output_parses():
    decision = BasirahBrainDecisionV1(confidence_score=42.0, targets=[100.0, 110.0, 120.0], **_BASE_KWARGS)
    assert decision.decision is BrainDecision.NO_TRADE
    assert decision.confidence_score == 42.0


def test_confidence_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(confidence_score=101.0, **_BASE_KWARGS)
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(confidence_score=-1.0, **_BASE_KWARGS)


def test_nan_and_infinite_confidence_rejected():
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(confidence_score=math.nan, **_BASE_KWARGS)
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(confidence_score=math.inf, **_BASE_KWARGS)


def test_entry_zone_low_must_not_exceed_high():
    from src.ai.basirah_brain.schemas import BrainEntryZone

    with pytest.raises(ValidationError):
        BrainEntryZone(low=110.0, high=100.0)
    # Valid, equal bounds are fine.
    BrainEntryZone(low=100.0, high=100.0)


def test_target_ordering_enforced():
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(confidence_score=50.0, targets=[120.0, 110.0, 100.0], **_BASE_KWARGS)
    # Non-decreasing order is accepted.
    decision = BasirahBrainDecisionV1(confidence_score=50.0, targets=[100.0, 110.0, 120.0], **_BASE_KWARGS)
    assert decision.targets == [100.0, 110.0, 120.0]


def test_targets_reject_nan():
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(confidence_score=50.0, targets=[math.nan], **_BASE_KWARGS)


def test_invalid_decision_enum_rejected():
    with pytest.raises(ValidationError):
        BasirahBrainDecisionV1(
            decision="STRONG_BUY_NOW",  # not a member of BrainDecision
            confidence_score=50.0,
            confidence_label=ConfidenceLabel.LOW,
            risk_level=BrainRiskLevel.MEDIUM,
            thesis_summary="test",
            data_quality=BrainDataQualityOut(sufficient=True),
            agreement_with_deterministic_engine=AgreementStatus.AGREE,
            deterministic_decision="REJECT",
            brain_decision="NO_TRADE",
        )


def test_key_evidence_requires_source_field():
    from src.ai.basirah_brain.schemas import BrainKeyEvidence

    with pytest.raises(ValidationError):
        BrainKeyEvidence(category="technical", statement="x")  # missing source_field
    item = BrainKeyEvidence(category="technical", statement="x", source_field="technical.trend_score")
    assert item.source_field == "technical.trend_score"
