"""AnalystEngine: the Autonomous AI Analyst Framework's entry point.

Sits above `AIDecisionEngine` (which itself sits above
`RecommendationEngine`, `TechnicalAnalysisEngine`, and
`FundamentalAnalysisEngine`) by calling `AIDecisionEngine.decide()` as
a black box and narrating its result -- this class computes no score,
target, or confidence value itself; every number in the resulting
`AnalystReport` comes from the `InvestmentDecision` it wraps.
"""

from datetime import datetime, timezone
from typing import Optional

from src.analysis.analyst.reasoning_pipeline import ReasoningPipeline
from src.analysis.analyst.types import AnalystReport
from src.analysis.decision.ai_decision_engine import AIDecisionEngine
from src.analysis.recommendation.types import AnalysisContext

# Recorded on every AnalystReport -- bump this when a change to this
# module or ReasoningPipeline would make an old report's wording no
# longer reproducible from its stored InvestmentDecision, the same
# discipline AIDecisionEngine.ENGINE_VERSION already applies one layer
# down.
ANALYST_ENGINE_VERSION = "1.0.0"


class AnalystEngine:
    """Pass a pre-configured `AIDecisionEngine` (e.g. with custom
    contributors or tuning) to change what feeds the report -- this
    class's own `analyze()` signature never changes either way. Pass a
    custom `ReasoningPipeline` (e.g. with an `LLMAdapter` injected) to
    change how the report is narrated, without touching this class's
    code."""

    def __init__(
        self,
        decision_engine: Optional[AIDecisionEngine] = None,
        pipeline: Optional[ReasoningPipeline] = None,
    ):
        self._decision_engine = decision_engine or AIDecisionEngine()
        self._pipeline = pipeline or ReasoningPipeline()

    async def analyze(self, context: AnalysisContext) -> AnalystReport:
        decision = self._decision_engine.decide(context)
        explanation = await self._pipeline.run(context, decision)
        return AnalystReport(
            symbol=context.symbol,
            decision=decision,
            explanation=explanation,
            generated_at=datetime.now(timezone.utc),
            engine_version=ANALYST_ENGINE_VERSION,
        )
