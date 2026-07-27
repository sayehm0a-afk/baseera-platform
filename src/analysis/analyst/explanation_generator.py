"""ExplanationGenerator: pure assembly of every prior pipeline stage's
output into one `Explanation`.

Computes nothing itself -- it only guarantees the twelve required
sections are always present, by reading each one from the stage that
already produced it (`NarrativeBuilder` for the prose sections,
`SignalInterpreter` for the bullish/bearish factor lists,
`ConflictResolver` for alternative scenarios, `ConfidenceValidator` for
the confidence explanation, `RecommendationComposer` for the summary
and final rationale).
"""

from src.analysis.analyst.types import (
    ConfidenceAssessment,
    ConflictAssessment,
    Evidence,
    Explanation,
    InterpretedSignals,
    RecommendationRationale,
)


class ExplanationGenerator:
    def generate(
        self,
        evidence: Evidence,
        interpreted: InterpretedSignals,
        conflict: ConflictAssessment,
        confidence_assessment: ConfidenceAssessment,
        rationale: RecommendationRationale,
        technical_reasoning: str,
        fundamental_reasoning: str,
        risk_explanation: str,
        target_price_explanation: str,
        stop_loss_explanation: str,
        time_horizon_explanation: str,
    ) -> Explanation:
        return Explanation(
            investment_summary=rationale.summary,
            technical_reasoning=technical_reasoning,
            fundamental_reasoning=fundamental_reasoning,
            risk_explanation=risk_explanation,
            bullish_factors=[f.description for f in interpreted.bullish_factors],
            bearish_factors=[f.description for f in interpreted.bearish_factors],
            confidence_explanation=confidence_assessment.narrative,
            target_price_explanation=target_price_explanation,
            stop_loss_explanation=stop_loss_explanation,
            time_horizon_explanation=time_horizon_explanation,
            alternative_scenarios=conflict.alternative_scenarios,
            final_recommendation_rationale=rationale.final_rationale,
        )
