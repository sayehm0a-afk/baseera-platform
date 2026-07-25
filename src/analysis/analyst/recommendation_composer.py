"""RecommendationComposer: synthesizes every earlier pipeline stage
into the report's two headline paragraphs -- the investment summary
and the final recommendation rationale.

Always deterministic, never LLM-eligible: these two sections are
precise, numeric-heavy syntheses of the whole decision (score,
confidence, conflict, top factors), exactly the kind of content where
a rephrasing pass would risk drifting from the underlying numbers.
"""

from typing import Optional

from src.analysis.analyst.prompt_templates import PromptTemplateManager
from src.analysis.analyst.types import (
    ConfidenceAssessment,
    ConflictAssessment,
    Evidence,
    InterpretedSignals,
    RecommendationRationale,
)


class RecommendationComposer:
    def __init__(self, template_manager: Optional[PromptTemplateManager] = None):
        self._templates = template_manager or PromptTemplateManager()

    def compose(
        self,
        evidence: Evidence,
        interpreted: InterpretedSignals,
        conflict: ConflictAssessment,
        confidence_assessment: ConfidenceAssessment,
    ) -> RecommendationRationale:
        decision = evidence.decision
        conflict_clause = (
            "However, the evidence shows some disagreement between categories, described below."
            if conflict.has_conflict
            else "The evidence is broadly aligned across analysis categories."
        )
        summary = self._templates.render(
            "investment_summary",
            symbol=evidence.symbol,
            recommendation=decision.recommendation.value.replace("_", " ").title(),
            confidence=decision.confidence,
            final_score=decision.final_score,
            conflict_clause=conflict_clause,
        )

        is_bullish_call = decision.final_score >= 50.0
        leading_factors = interpreted.bullish_factors if is_bullish_call else interpreted.bearish_factors
        if leading_factors:
            top_factor_clause = f"The strongest driver is: {leading_factors[0].description.rstrip('.')}. "
        else:
            top_factor_clause = ""
        conflict_tail = f" {conflict.narrative}" if conflict.has_conflict else ""

        final_rationale = self._templates.render(
            "final_rationale",
            recommendation=decision.recommendation.value.replace("_", " ").title(),
            symbol=evidence.symbol,
            final_score=decision.final_score,
            confidence=decision.confidence,
            top_factor_clause=top_factor_clause,
            conflict_tail=conflict_tail,
        )

        return RecommendationRationale(summary=summary, final_rationale=final_rationale)
