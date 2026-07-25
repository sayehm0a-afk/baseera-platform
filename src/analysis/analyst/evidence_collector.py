"""EvidenceCollector: assembles `Evidence` from an already-computed
`AnalysisContext`/`InvestmentDecision` pair.

Pure reorganization -- it reads fields that already exist and performs
zero calculation of its own, exactly the same "orchestration, not
computation" discipline `RecommendationEngine`/`AIDecisionEngine`
already apply one layer down.
"""

from src.analysis.analyst.types import Evidence
from src.analysis.decision.types import InvestmentDecision
from src.analysis.recommendation.types import AnalysisContext


class EvidenceCollector:
    def collect(self, context: AnalysisContext, decision: InvestmentDecision) -> Evidence:
        return Evidence(
            symbol=context.symbol,
            decision=decision,
            technical_result=context.technical_result,
            fundamental_result=context.fundamental_result,
            signals=decision.signals,
            contributor_breakdown=decision.breakdown,
        )
