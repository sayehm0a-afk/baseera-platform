"""Unit tests for RecommendationBuilder -- pure assembly."""

from datetime import datetime, timezone

from src.portfolio_intelligence.recommendation_builder import RecommendationBuilder
from src.portfolio_intelligence.types import (
    CashRecommendation,
    OptimizationRecommendation,
    PositionAction,
    RebalanceAction,
    RebalancePlan,
)

_NOW = datetime.now(timezone.utc)


def test_build_assembles_every_field_unchanged():
    action = RebalanceAction(symbol="A", action=PositionAction.HOLD, current_weight=0.1, rationale="r")
    plan = RebalancePlan(actions=[action], new_buy_opportunities=[], generated_at=_NOW, new_buy_opportunities_source="test")
    cash = CashRecommendation(
        current_cash=100.0, current_cash_pct=0.1, recommended_cash_pct_min=0.05, recommended_cash_pct_max=0.15,
        recommended_cash_amount_min=50.0, recommended_cash_amount_max=150.0, is_within_target_band=True, rationale="cash",
    )
    optimization = [OptimizationRecommendation(priority=1, title="t", rationale="r")]

    recommendations = RecommendationBuilder().build(plan, cash, optimization)

    assert recommendations.rebalance_actions == [action]
    assert recommendations.new_buy_opportunities == []
    assert recommendations.cash_recommendation is cash
    assert recommendations.optimization_recommendations == optimization
    assert recommendations.generated_at is not None
