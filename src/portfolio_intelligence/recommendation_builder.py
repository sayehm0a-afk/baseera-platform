"""RecommendationBuilder: pure assembly of the final
`PortfolioRecommendations` -- rebalance actions and new-buy
opportunities from `RebalanceEngine`, the cash recommendation from
`CashManager`, and prioritized recommendations from
`OptimizationEngine`. Computes nothing; guarantees every field is
always populated, the same "pure assembly" role
`src.analysis.analyst.explanation_generator.ExplanationGenerator`
plays one milestone down.
"""

from datetime import datetime, timezone
from typing import List

from src.portfolio_intelligence.types import (
    CashRecommendation,
    OptimizationRecommendation,
    PortfolioRecommendations,
    RebalancePlan,
)


class RecommendationBuilder:
    def build(
        self,
        rebalance_plan: RebalancePlan,
        cash_recommendation: CashRecommendation,
        optimization_recommendations: List[OptimizationRecommendation],
    ) -> PortfolioRecommendations:
        return PortfolioRecommendations(
            rebalance_actions=rebalance_plan.actions,
            new_buy_opportunities=rebalance_plan.new_buy_opportunities,
            cash_recommendation=cash_recommendation,
            optimization_recommendations=optimization_recommendations,
            generated_at=datetime.now(timezone.utc),
        )
