"""BasirahBrainService: the orchestration boundary for Stage 1.

`analyze_shadow()` is the ONLY entry point this module exposes, and it
does exactly the nine steps the mandate requires -- build input, validate
input (structural validation happens automatically at
`BasirahBrainInputV1` construction), enforce the deterministic hard-gate
policy, call the provider, validate structured output, enforce
post-generation safety constraints, record an isolated Shadow result,
and return a typed result.

Hard isolation guarantee (verified by never importing the relevant
modules, not merely by convention): this service imports nothing from
`src.analysis.decision_v2.gates`/`engine` (it never recomputes or
mutates a decision), nothing that writes `DecisionV2Snapshot`,
`RadarOpportunity`, or `ShadowLiveSignal`, and calls no SAHMK/provider
client of any kind -- it only reads an already-computed `DecisionResult`
handed to it by the caller.
"""

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from sqlalchemy.orm import Session

from src.analysis.decision_v2.types import DecisionResult
from src.domain.models import BasirahBrainShadowDecision, Stock

from .evidence_builder import build_input
from .prompts import PROMPT_VERSION
from .provider import BasirahBrainProvider
from .schemas import BasirahBrainDecisionV1, BasirahBrainInputV1
from .telemetry import compute_input_hash
from .validators import apply_all_safety_corrections

logger = logging.getLogger(__name__)

STATUS_SUCCESS = "SUCCESS"
STATUS_PROVIDER_ERROR = "PROVIDER_ERROR"
STATUS_INVALID_OUTPUT = "INVALID_OUTPUT"
STATUS_POLICY_VIOLATION_CORRECTED = "POLICY_VIOLATION_CORRECTED"


@dataclass(frozen=True)
class ShadowAnalysisResult:
    status: str
    decision: Optional[BasirahBrainDecisionV1]
    shadow_record_id: Optional[int]
    error_code: Optional[str]
    reason_codes: List[str]


class BasirahBrainService:
    def __init__(
        self,
        provider: BasirahBrainProvider,
        session_factory: Callable[[], Session],
        prompt_version: str = PROMPT_VERSION,
    ):
        self._provider = provider
        self._session_factory = session_factory
        self._prompt_version = prompt_version

    async def analyze_shadow(
        self,
        decision_result: DecisionResult,
        stock: Stock,
        *,
        daily_bars: Optional[Sequence[object]] = None,
        weekly_bars: Optional[Sequence[object]] = None,
        news_headlines: Optional[Sequence[object]] = None,
        index_direction: Optional[str] = None,
        index_strength: Optional[float] = None,
        sector_performance: Optional[str] = None,
        breakout_status: Optional[str] = None,
    ) -> ShadowAnalysisResult:
        brain_input = build_input(
            decision_result,
            stock,
            daily_bars=daily_bars,
            weekly_bars=weekly_bars,
            news_headlines=news_headlines,
            index_direction=index_direction,
            index_strength=index_strength,
            sector_performance=sector_performance,
            breakout_status=breakout_status,
        )

        outcome = await self._provider.analyze(brain_input)

        if not outcome.success:
            record_id = self._persist(
                brain_input=brain_input,
                stock=stock,
                decision_result=decision_result,
                model_provider=outcome.model_provider,
                model_name=outcome.model_name,
                output_schema_version=None,
                brain_decision=None,
                brain_confidence_score=None,
                agreement_status=None,
                reason_codes=[],
                raw_structured_output=None,
                latency_ms=outcome.latency_ms,
                status=STATUS_PROVIDER_ERROR,
                error_code=outcome.error_code,
            )
            logger.info(
                "Basirah Brain Shadow analysis for '%s' failed at the provider layer (%s).",
                decision_result.symbol,
                outcome.error_code,
            )
            return ShadowAnalysisResult(
                status=STATUS_PROVIDER_ERROR,
                decision=None,
                shadow_record_id=record_id,
                error_code=outcome.error_code,
                reason_codes=[],
            )

        corrected, notes = apply_all_safety_corrections(brain_input, outcome.decision)
        policy_corrected = any("Corrected brain_decision" in note for note in notes)
        status = STATUS_POLICY_VIOLATION_CORRECTED if policy_corrected else STATUS_SUCCESS
        if notes:
            logger.warning(
                "Basirah Brain Shadow analysis for '%s' required post-generation correction: %s",
                decision_result.symbol,
                "; ".join(notes),
            )

        record_id = self._persist(
            brain_input=brain_input,
            stock=stock,
            decision_result=decision_result,
            model_provider=outcome.model_provider,
            model_name=outcome.model_name,
            output_schema_version=corrected.schema_version,
            brain_decision=corrected.decision.value,
            brain_confidence_score=corrected.confidence_score,
            agreement_status=corrected.agreement_with_deterministic_engine.value,
            reason_codes=corrected.reason_codes,
            raw_structured_output=corrected.model_dump(mode="json"),
            latency_ms=outcome.latency_ms,
            status=status,
            error_code=None,
        )

        return ShadowAnalysisResult(
            status=status,
            decision=corrected,
            shadow_record_id=record_id,
            error_code=None,
            reason_codes=corrected.reason_codes,
        )

    def _persist(
        self,
        *,
        brain_input: BasirahBrainInputV1,
        stock: Stock,
        decision_result: DecisionResult,
        model_provider: str,
        model_name: str,
        output_schema_version: Optional[str],
        brain_decision: Optional[str],
        brain_confidence_score: Optional[float],
        agreement_status: Optional[str],
        reason_codes: List[str],
        raw_structured_output: Optional[dict],
        latency_ms: float,
        status: str,
        error_code: Optional[str],
    ) -> int:
        input_hash = compute_input_hash(brain_input)

        session = self._session_factory()
        try:
            row = BasirahBrainShadowDecision(
                symbol=decision_result.symbol,
                stock_id=stock.id,
                decision_v2_snapshot_id=None,
                input_schema_version=brain_input.schema_version,
                output_schema_version=output_schema_version,
                model_provider=model_provider,
                model_name=model_name,
                prompt_version=self._prompt_version,
                input_hash=input_hash,
                deterministic_decision=decision_result.decision.value,
                brain_decision=brain_decision,
                brain_confidence_score=brain_confidence_score,
                agreement_status=agreement_status,
                reason_codes=reason_codes,
                raw_structured_output=raw_structured_output,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
        finally:
            session.close()
