"""ReasoningPipeline: orchestrates every Autonomous AI Analyst
Framework stage into one `Explanation`.

`async def run()` exists solely to support the optional `LLMAdapter`
extension point -- three sections (technical/fundamental reasoning,
risk explanation) are, when an adapter is injected, offered to it for
rephrasing after the deterministic baseline is already computed, so a
failure or slow response from that step never blocks report
generation on its own; every other section is always produced
deterministically. No adapter is injected by default, so
`AnalystEngine`'s production path never calls out to any external
model -- see `llm_adapter.py`.
"""

from typing import Optional

from src.analysis.analyst.confidence_validator import ConfidenceValidator
from src.analysis.analyst.conflict_resolver import ConflictResolver
from src.analysis.analyst.evidence_collector import EvidenceCollector
from src.analysis.analyst.explanation_generator import ExplanationGenerator
from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationRequest
from src.analysis.analyst.narrative_builder import NarrativeBuilder
from src.analysis.analyst.prompt_templates import PromptTemplateManager
from src.analysis.analyst.recommendation_composer import RecommendationComposer
from src.analysis.analyst.signal_interpreter import SignalInterpreter
from src.analysis.analyst.types import Explanation
from src.analysis.decision.types import InvestmentDecision
from src.analysis.recommendation.types import AnalysisContext


class ReasoningPipeline:
    def __init__(
        self,
        evidence_collector: Optional[EvidenceCollector] = None,
        signal_interpreter: Optional[SignalInterpreter] = None,
        conflict_resolver: Optional[ConflictResolver] = None,
        confidence_validator: Optional[ConfidenceValidator] = None,
        narrative_builder: Optional[NarrativeBuilder] = None,
        recommendation_composer: Optional[RecommendationComposer] = None,
        explanation_generator: Optional[ExplanationGenerator] = None,
        template_manager: Optional[PromptTemplateManager] = None,
        llm_adapter: Optional[LLMAdapter] = None,
    ):
        self._template_manager = template_manager or PromptTemplateManager()
        self._evidence_collector = evidence_collector or EvidenceCollector()
        self._signal_interpreter = signal_interpreter or SignalInterpreter()
        self._conflict_resolver = conflict_resolver or ConflictResolver()
        self._confidence_validator = confidence_validator or ConfidenceValidator()
        self._narrative_builder = narrative_builder or NarrativeBuilder(self._template_manager)
        self._recommendation_composer = recommendation_composer or RecommendationComposer(self._template_manager)
        self._explanation_generator = explanation_generator or ExplanationGenerator()
        self._llm_adapter = llm_adapter

    async def run(self, context: AnalysisContext, decision: InvestmentDecision) -> Explanation:
        evidence = self._evidence_collector.collect(context, decision)
        interpreted = self._signal_interpreter.interpret(evidence)
        conflict = self._conflict_resolver.resolve(evidence, interpreted)
        confidence_assessment = self._confidence_validator.validate(evidence, conflict)

        technical_reasoning = await self._narrate(
            "technical_reasoning", self._narrative_builder.build_technical_reasoning(evidence, interpreted)
        )
        fundamental_reasoning = await self._narrate(
            "fundamental_reasoning", self._narrative_builder.build_fundamental_reasoning(evidence, interpreted)
        )
        risk_explanation = await self._narrate(
            "risk_explanation", self._narrative_builder.build_risk_explanation(evidence, interpreted)
        )
        target_price_explanation = self._narrative_builder.build_target_price_explanation(evidence)
        stop_loss_explanation = self._narrative_builder.build_stop_loss_explanation(evidence)
        time_horizon_explanation = self._narrative_builder.build_time_horizon_explanation(evidence)

        rationale = self._recommendation_composer.compose(evidence, interpreted, conflict, confidence_assessment)

        return self._explanation_generator.generate(
            evidence,
            interpreted,
            conflict,
            confidence_assessment,
            rationale,
            technical_reasoning,
            fundamental_reasoning,
            risk_explanation,
            target_price_explanation,
            stop_loss_explanation,
            time_horizon_explanation,
        )

    async def _narrate(self, section_name: str, baseline_text: str) -> str:
        """Returns the deterministic `baseline_text` unless an
        `LLMAdapter` was injected, in which case that baseline is
        offered to the adapter for rephrasing and its result used only
        if non-empty -- the baseline is always the safe fallback,
        never replaced by nothing."""
        if self._llm_adapter is None:
            return baseline_text
        prompt = self._template_manager.build_prompt(section_name, baseline_text)
        result = await self._llm_adapter.generate(LLMGenerationRequest(prompt=prompt))
        return result.text if result.text else baseline_text
