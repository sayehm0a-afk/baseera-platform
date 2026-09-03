"""Pre-merge hardening audit -- durable regression tests for the
adversarial cases the remediation mandate specifically required beyond
what test_validators.py already covers in isolation: F2/F3 sanitization
through the REAL service pipeline, and F6 bounded-output edge cases
(exactly-at-limit, over-limit, unicode/Arabic text)."""

import pytest
from pydantic import ValidationError

from src.ai.basirah_brain.providers.mock_provider import MockBasirahBrainProvider
from src.ai.basirah_brain.schemas import (
    AgreementStatus,
    BasirahBrainDecisionV1,
    BrainDataQualityOut,
    BrainDecision,
    BrainKeyEvidence,
    BrainRiskLevel,
    ConfidenceLabel,
)
from src.ai.basirah_brain.service import STATUS_PROVIDER_ERROR, STATUS_SUCCESS, BasirahBrainService

from .conftest import make_decision_result


def _watch_response(_):
    return (
        '{"decision":"WATCH","confidence_score":50,"confidence_label":"MEDIUM","entry_zone":{},'
        '"stop_loss":null,"targets":[],"holding_horizon":{},"risk_level":"MEDIUM","thesis_summary":"x",'
        '"key_evidence":[{"category":"x","statement":"x","source_field":"technical.fabricated_indicator_xyz"}],'
        '"reason_codes":["TOTALLY_MADE_UP_CODE"],'
        '"data_quality":{"sufficient":true},"agreement_with_deterministic_engine":"AGREE",'
        '"deterministic_decision":"WATCH","brain_decision":"WATCH"}'
    )


@pytest.mark.asyncio
async def test_invented_source_field_and_reason_code_sanitized_through_real_service(session_factory, stock):
    from src.analysis.decision_v2.types import Decision

    dr = make_decision_result(decision=Decision.WATCH)
    service = BasirahBrainService(provider=MockBasirahBrainProvider(response_factory=_watch_response), session_factory=session_factory)

    result = await service.analyze_shadow(dr, stock)

    assert result.status == STATUS_SUCCESS
    assert result.decision.key_evidence == []  # fabricated citation removed
    assert result.decision.data_quality.sufficient is False
    assert "TOTALLY_MADE_UP_CODE" not in result.decision.reason_codes
    assert "OTHER_UNVALIDATED_REASON" in result.decision.reason_codes


def _base_kwargs(**overrides):
    base = dict(
        decision=BrainDecision.NO_TRADE,
        confidence_score=50.0,
        confidence_label=ConfidenceLabel.LOW,
        risk_level=BrainRiskLevel.LOW,
        thesis_summary="x",
        data_quality=BrainDataQualityOut(sufficient=True),
        agreement_with_deterministic_engine=AgreementStatus.AGREE,
        deterministic_decision="REJECT",
        brain_decision="NO_TRADE",
    )
    base.update(overrides)
    return base


class TestF6BoundedOutputs:
    def test_normal_text_accepted(self):
        BasirahBrainDecisionV1(**_base_kwargs(thesis_summary="A perfectly ordinary, short analyst summary."))

    def test_exactly_at_limit_accepted(self):
        BasirahBrainDecisionV1(**_base_kwargs(thesis_summary="x" * 3000))
        BrainKeyEvidence(category="x", statement="x" * 300, source_field="x")

    def test_over_limit_rejected(self):
        with pytest.raises(ValidationError):
            BasirahBrainDecisionV1(**_base_kwargs(thesis_summary="x" * 3001))
        with pytest.raises(ValidationError):
            BrainKeyEvidence(category="x", statement="x" * 301, source_field="x")

    def test_huge_malicious_payload_rejected(self):
        with pytest.raises(ValidationError):
            BasirahBrainDecisionV1(**_base_kwargs(thesis_summary="A" * 100_000))

    def test_oversized_list_rejected(self):
        with pytest.raises(ValidationError):
            BasirahBrainDecisionV1(**_base_kwargs(bull_case=["x"] * 1000))

    def test_unicode_arabic_text_within_bounds_accepted(self):
        arabic = "الاتجاه العام صاعد بقوة والسيولة جيدة والمخاطر منخفضة نسبيًا"
        decision = BasirahBrainDecisionV1(**_base_kwargs(thesis_summary=arabic, bull_case=[arabic]))
        assert decision.thesis_summary == arabic

    def test_unicode_arabic_text_over_limit_rejected(self):
        arabic_huge = "نص طويل جدا " * 2000
        assert len(arabic_huge) > 3000
        with pytest.raises(ValidationError):
            BasirahBrainDecisionV1(**_base_kwargs(thesis_summary=arabic_huge))


@pytest.mark.asyncio
async def test_oversized_provider_response_fails_closed_through_real_service(session_factory, stock):
    from src.analysis.decision_v2.types import Decision
    import json

    def huge_response(_):
        return json.dumps(
            {
                "decision": "WATCH", "confidence_score": 50, "confidence_label": "MEDIUM", "entry_zone": {},
                "stop_loss": None, "targets": [], "holding_horizon": {}, "risk_level": "MEDIUM",
                "thesis_summary": "A" * 100_000,
                "data_quality": {"sufficient": True}, "agreement_with_deterministic_engine": "AGREE",
                "deterministic_decision": "WATCH", "brain_decision": "WATCH",
            }
        )

    dr = make_decision_result(decision=Decision.WATCH)
    service = BasirahBrainService(provider=MockBasirahBrainProvider(response_factory=huge_response), session_factory=session_factory)
    result = await service.analyze_shadow(dr, stock)
    assert result.status == STATUS_PROVIDER_ERROR
    assert result.error_code == "SCHEMA_VALIDATION_FAILED"
