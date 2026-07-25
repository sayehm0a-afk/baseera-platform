"""Unit tests for OptimizationEngine."""

from datetime import datetime, timezone

from src.analysis.decision.types import RiskLevel
from src.portfolio_intelligence.optimization_engine import OptimizationEngine
from src.portfolio_intelligence.types import (
    CashRecommendation,
    ConcentrationRisk,
    DiversificationScore,
    PortfolioRiskProfile,
    PositionAction,
    RebalanceAction,
    RebalancePlan,
)

_NOW = datetime.now(timezone.utc)


def _concentration(is_concentrated=False):
    return ConcentrationRisk(
        herfindahl_index=0.2, sector_herfindahl_index=0.2, largest_position_symbol="A" if is_concentrated else None,
        largest_position_weight=0.4 if is_concentrated else None, top_3_weight=0.6, is_concentrated=is_concentrated,
        concentration_threshold=0.25,
    )


def _diversification(score=80.0):
    return DiversificationScore(score=score, effective_number_of_holdings=5.0, effective_number_of_sectors=3.0, sector_count=3, holdings_count=5, narrative="narrative text")


def _risk(risk_level=RiskLevel.LOW):
    return PortfolioRiskProfile(
        risk_score=20.0, risk_level=risk_level, expected_volatility_annualized_pct=10.0, estimated_max_drawdown_pct=5.0,
        portfolio_beta=None, beta_unavailable_reason="n/a", correlation_matrix=None, excluded_from_volatility=[],
        narrative="risk narrative",
    )


def _cash(within_band=True):
    return CashRecommendation(
        current_cash=1000.0, current_cash_pct=0.10, recommended_cash_pct_min=0.05, recommended_cash_pct_max=0.15,
        recommended_cash_amount_min=500.0, recommended_cash_amount_max=1500.0, is_within_target_band=within_band,
        rationale="cash rationale",
    )


def _plan(actions=(), new_buys=()):
    return RebalancePlan(actions=list(actions), new_buy_opportunities=list(new_buys), generated_at=_NOW, new_buy_opportunities_source="test")


def test_no_issues_yields_a_single_no_change_recommendation():
    recommendations = OptimizationEngine().build(_concentration(False), _diversification(90.0), _risk(), _cash(True), _plan())
    assert len(recommendations) == 1
    assert recommendations[0].title == "No changes indicated"


def test_concentration_flagged_first():
    recommendations = OptimizationEngine().build(_concentration(True), _diversification(90.0), _risk(), _cash(True), _plan())
    assert recommendations[0].title == "Reduce concentration in A"
    assert recommendations[0].priority == 1


def test_exits_and_reductions_surfaced():
    action = RebalanceAction(symbol="X", action=PositionAction.EXIT, current_weight=0.1, rationale="exit rationale")
    recommendations = OptimizationEngine().build(_concentration(False), _diversification(90.0), _risk(), _cash(True), _plan(actions=[action]))
    titles = [r.title for r in recommendations]
    assert "Exit X" in titles


def test_very_high_risk_surfaced():
    recommendations = OptimizationEngine().build(_concentration(False), _diversification(90.0), _risk(RiskLevel.VERY_HIGH), _cash(True), _plan())
    assert any(r.title == "Reduce overall portfolio risk" for r in recommendations)


def test_low_diversification_surfaced():
    recommendations = OptimizationEngine().build(_concentration(False), _diversification(20.0), _risk(), _cash(True), _plan())
    assert any(r.title == "Increase diversification" for r in recommendations)


def test_cash_out_of_band_surfaced():
    recommendations = OptimizationEngine().build(_concentration(False), _diversification(90.0), _risk(), _cash(False), _plan())
    assert any(r.title == "Rebalance cash reserve" for r in recommendations)


def test_priorities_are_sequential_starting_at_one():
    action = RebalanceAction(symbol="X", action=PositionAction.REDUCE, current_weight=0.3, rationale="r")
    recommendations = OptimizationEngine().build(_concentration(True), _diversification(20.0), _risk(RiskLevel.VERY_HIGH), _cash(False), _plan(actions=[action]))
    assert [r.priority for r in recommendations] == list(range(1, len(recommendations) + 1))
