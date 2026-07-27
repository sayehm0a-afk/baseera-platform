"""OptimizationEngine: synthesizes prioritized, human-readable
portfolio optimization recommendations from already-computed portfolio-
level results (`ConcentrationRisk`, `DiversificationScore`,
`PortfolioRiskProfile`, `CashRecommendation`, `RebalancePlan`) --
mirrors `src.analysis.analyst.recommendation_composer.
RecommendationComposer`'s role one milestone down: it synthesizes, it
never recomputes any of the numbers it cites.
"""

from typing import List

from src.portfolio_intelligence.types import (
    CashRecommendation,
    ConcentrationRisk,
    DiversificationScore,
    OptimizationRecommendation,
    PortfolioRiskProfile,
    PositionAction,
    RebalancePlan,
)

_LOW_DIVERSIFICATION_SCORE_THRESHOLD = 50.0


class OptimizationEngine:
    def build(
        self,
        concentration: ConcentrationRisk,
        diversification: DiversificationScore,
        risk_profile: PortfolioRiskProfile,
        cash_recommendation: CashRecommendation,
        rebalance_plan: RebalancePlan,
    ) -> List[OptimizationRecommendation]:
        recommendations: List[OptimizationRecommendation] = []

        if concentration.is_concentrated:
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title=f"Reduce concentration in {concentration.largest_position_symbol}",
                    rationale=(
                        f"{concentration.largest_position_symbol} is {concentration.largest_position_weight * 100:.1f}% "
                        f"of the portfolio, above the {concentration.concentration_threshold * 100:.0f}% concentration "
                        "threshold -- a single adverse move in this holding would disproportionately affect the "
                        "whole portfolio."
                    ),
                )
            )

        exits_and_reductions = [a for a in rebalance_plan.actions if a.action in (PositionAction.EXIT, PositionAction.REDUCE)]
        for action in exits_and_reductions:
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title=f"{action.action.value.title()} {action.symbol}",
                    rationale=action.rationale,
                )
            )

        if risk_profile.risk_level.value == "VERY_HIGH":
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title="Reduce overall portfolio risk",
                    rationale=risk_profile.narrative,
                )
            )

        if diversification.score < _LOW_DIVERSIFICATION_SCORE_THRESHOLD:
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title="Increase diversification",
                    rationale=(
                        f"Diversification score is {diversification.score:.1f}/100 -- "
                        f"{diversification.narrative}"
                    ),
                )
            )

        if not cash_recommendation.is_within_target_band:
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title="Rebalance cash reserve",
                    rationale=cash_recommendation.rationale,
                )
            )

        increases = [a for a in rebalance_plan.actions if a.action is PositionAction.INCREASE]
        for action in increases:
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title=f"Consider increasing {action.symbol}",
                    rationale=action.rationale,
                )
            )

        if rebalance_plan.new_buy_opportunities:
            top = rebalance_plan.new_buy_opportunities[0]
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title=f"Consider a new position in {top.symbol}",
                    rationale=top.rationale,
                )
            )

        if not recommendations:
            recommendations.append(
                OptimizationRecommendation(
                    priority=0,
                    title="No changes indicated",
                    rationale="Allocation, diversification, risk, and cash are all within their target ranges.",
                )
            )

        for index, recommendation in enumerate(recommendations, start=1):
            recommendations[index - 1] = OptimizationRecommendation(
                priority=index, title=recommendation.title, rationale=recommendation.rationale
            )
        return recommendations
