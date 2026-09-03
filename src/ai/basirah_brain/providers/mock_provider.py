"""MockBasirahBrainProvider: the no-LLM, no-network provider used by
every test and safe for local development (Stage 1 requirement F).

`response_factory(brain_input) -> str` produces the raw JSON text the
"model" would have returned; it may also raise to simulate a provider
failure (timeout, connection error, malformed output). The default
factory (`default_conservative_response`) is a simple, honest,
rule-based mirror of the deterministic engine's own decision -- it never
tries to be a real analyst, only a deterministic stand-in that exercises
the full validation/persistence pipeline in tests without ever making it
look like real AI reasoning.
"""

import json
import time
from typing import Callable, Optional

from ..schemas import (
    AgreementStatus,
    BasirahBrainDecisionV1,
    BrainDecision,
    ConfidenceLabel,
    BrainRiskLevel,
    BasirahBrainInputV1,
    SCHEMA_VERSION,
)
from ..provider import BasirahBrainProviderOutcome

ResponseFactory = Callable[[BasirahBrainInputV1], str]

_BUY_FAMILY = {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"}


def default_conservative_response(brain_input: BasirahBrainInputV1) -> str:
    """A deliberately simple, deterministic mirror of the existing
    engine's own decision -- agrees when the deterministic decision is
    actionable and evidence is clean, otherwise NO_TRADE. This is a test
    fixture, not a stand-in for real synthesis."""
    engine = brain_input.existing_engine
    stale = bool(brain_input.data_quality.stale_flags) or brain_input.data_quality.is_synthetic

    if engine.deterministic_decision in _BUY_FAMILY and not stale:
        decision = BrainDecision.BUY
        agreement = AgreementStatus.AGREE
        confidence = min(100.0, max(0.0, engine.deterministic_confidence_score))
    elif engine.deterministic_decision in _BUY_FAMILY and stale:
        decision = BrainDecision.NO_TRADE
        agreement = AgreementStatus.MORE_CONSERVATIVE
        confidence = 20.0
    elif engine.deterministic_decision in {"WAIT_FOR_ENTRY", "WATCH"}:
        decision = BrainDecision.WATCH
        agreement = AgreementStatus.AGREE
        confidence = 40.0
    else:
        decision = BrainDecision.NO_TRADE
        agreement = AgreementStatus.AGREE
        confidence = 10.0

    payload = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision.value,
        "confidence_score": confidence,
        "confidence_label": (
            ConfidenceLabel.HIGH.value
            if confidence >= 70
            else ConfidenceLabel.MEDIUM.value if confidence >= 40 else ConfidenceLabel.LOW.value
        ),
        "entry_zone": {"low": engine.entry_zone_low, "high": engine.entry_zone_high},
        "stop_loss": engine.stop_loss,
        "targets": [t for t in (engine.target_1, engine.target_2, engine.target_3) if t is not None],
        "holding_horizon": {
            "min_days": engine.holding_horizon_min_days,
            "max_days": engine.holding_horizon_max_days,
        },
        "risk_level": BrainRiskLevel.MEDIUM.value,
        "thesis_summary": f"Mock synthesis mirroring deterministic decision {engine.deterministic_decision}.",
        "bull_case": [],
        "bear_case": [],
        "key_evidence": [
            {
                "category": "engine",
                "statement": f"Deterministic decision was {engine.deterministic_decision}.",
                "source_field": "existing_engine.deterministic_decision",
            }
        ],
        "invalidation_conditions": list(engine.invalidation_conditions),
        "monitoring_conditions": [],
        "data_quality": {
            "sufficient": not stale,
            "missing_critical_fields": [],
            "stale_inputs": list(brain_input.data_quality.stale_flags),
        },
        "agreement_with_deterministic_engine": agreement.value,
        "deterministic_decision": engine.deterministic_decision,
        "brain_decision": decision.value,
        "reason_codes": [],
    }
    return json.dumps(payload)


def hard_gate_override_attempt_response(brain_input: BasirahBrainInputV1) -> str:
    """Test fixture for CASE F: simulates a misbehaving model that
    attempts to output BUY despite a deterministic hard rejection --
    used to prove validators.py's post-generation policy enforcement
    actually corrects this rather than trusting the model."""
    payload = json.loads(default_conservative_response(brain_input))
    payload["decision"] = BrainDecision.BUY.value
    payload["brain_decision"] = BrainDecision.BUY.value
    payload["confidence_score"] = 95.0
    payload["entry_zone"] = {"low": 999.0, "high": 1000.0}  # also attempts invented price levels
    payload["stop_loss"] = 950.0
    payload["targets"] = [1010.0, 1020.0, 1030.0]
    return json.dumps(payload)


def malformed_json_response(_: BasirahBrainInputV1) -> str:
    return "{not valid json"


def prompt_injection_response(brain_input: BasirahBrainInputV1) -> str:
    """Test fixture proving news text cannot redirect the provider --
    the mock deliberately ignores any embedded instruction and returns
    a normal, schema-valid conservative response."""
    return default_conservative_response(brain_input)


class MockBasirahBrainProvider:
    """No-network stand-in satisfying `BasirahBrainProvider`."""

    def __init__(
        self,
        response_factory: Optional[ResponseFactory] = None,
        *,
        model_name: str = "mock-basirah-brain-v1",
    ):
        self._response_factory = response_factory or default_conservative_response
        self.model_name = model_name

    async def analyze(self, brain_input: BasirahBrainInputV1) -> BasirahBrainProviderOutcome:
        start = time.monotonic()
        try:
            raw = self._response_factory(brain_input)
        except Exception as exc:  # noqa: BLE001 -- provider failures must never propagate
            latency_ms = (time.monotonic() - start) * 1000
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=None,
                error_code=f"PROVIDER_EXCEPTION:{type(exc).__name__}",
                model_provider="mock",
                model_name=self.model_name,
                latency_ms=latency_ms,
            )
        latency_ms = (time.monotonic() - start) * 1000

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=raw,
                error_code="INVALID_JSON",
                model_provider="mock",
                model_name=self.model_name,
                latency_ms=latency_ms,
            )

        try:
            decision = BasirahBrainDecisionV1.model_validate(parsed)
        except Exception:  # noqa: BLE001 -- pydantic ValidationError, fail closed
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=raw,
                error_code="SCHEMA_VALIDATION_FAILED",
                model_provider="mock",
                model_name=self.model_name,
                latency_ms=latency_ms,
            )

        return BasirahBrainProviderOutcome(
            success=True,
            decision=decision,
            raw_content=raw,
            error_code=None,
            model_provider="mock",
            model_name=self.model_name,
            latency_ms=latency_ms,
        )
