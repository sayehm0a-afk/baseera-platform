"""Unit tests for PortfolioScore."""

from datetime import datetime, timezone

from src.analysis.decision.types import RiskLevel
from src.analysis.recommendation.types import Recommendation
from src.portfolio_intelligence.portfolio_score import PortfolioScore
from src.portfolio_intelligence.types import CashRecommendation, DiversificationScore, HealthBand, PortfolioRiskProfile
from tests.unit.portfolio_intelligence._fixtures import make_decision, make_holding_analysis

_NOW = datetime.now(timezone.utc)


def _diversification(score=80.0):
    return DiversificationScore(score=score, effective_number_of_holdings=5.0, effective_number_of_sectors=3.0, sector_count=3, holdings_count=5, narrative="")


def _risk(risk_score=20.0):
    return PortfolioRiskProfile(
        risk_score=risk_score, risk_level=RiskLevel.LOW, expected_volatility_annualized_pct=10.0,
        estimated_max_drawdown_pct=5.0, portfolio_beta=None, beta_unavailable_reason="n/a",
        correlation_matrix=None, excluded_from_volatility=[], narrative="",
    )


def _cash(within_band=True):
    return CashRecommendation(
        current_cash=1000.0, current_cash_pct=0.10, recommended_cash_pct_min=0.05, recommended_cash_pct_max=0.15,
        recommended_cash_amount_min=500.0, recommended_cash_amount_max=1500.0, is_within_target_band=within_band,
        rationale="",
    )


def test_high_diversification_low_risk_within_band_yields_high_score():
    holdings = [make_holding_analysis(symbol="A", weight=1.0, decision=make_decision(symbol="A", recommendation=Recommendation.BUY))]
    result = PortfolioScore().compute(_diversification(90.0), _risk(10.0), _cash(True), holdings)
    assert result.score > 70.0
    assert result.band in (HealthBand.GOOD, HealthBand.EXCELLENT)


def test_low_diversification_high_risk_yields_low_score():
    holdings = [make_holding_analysis(symbol="A", weight=1.0, decision=make_decision(symbol="A", recommendation=Recommendation.SELL))]
    result = PortfolioScore().compute(_diversification(10.0), _risk(90.0), _cash(False), holdings)
    assert result.score < 50.0


def test_components_sum_to_the_overall_score_via_configured_weights(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION", "1.0")
    monkeypatch.setenv("PORTFOLIO_HEALTH_WEIGHT_RISK", "0.0")
    monkeypatch.setenv("PORTFOLIO_HEALTH_WEIGHT_CASH", "0.0")
    monkeypatch.setenv("PORTFOLIO_HEALTH_WEIGHT_ALIGNMENT", "0.0")
    holdings = [make_holding_analysis(symbol="A", weight=1.0, decision=make_decision(symbol="A"))]
    result = PortfolioScore().compute(_diversification(64.0), _risk(0.0), _cash(True), holdings)
    assert result.score == 64.0


def test_recommendation_alignment_reflects_favorable_weight():
    holdings = [
        make_holding_analysis(symbol="A", weight=0.5, decision=make_decision(symbol="A", recommendation=Recommendation.BUY)),
        make_holding_analysis(symbol="B", weight=0.5, decision=make_decision(symbol="B", recommendation=Recommendation.SELL)),
    ]
    result = PortfolioScore().compute(_diversification(), _risk(), _cash(), holdings)
    assert result.components["recommendation_alignment"] == 50.0


def test_no_available_holdings_uses_a_neutral_alignment_default():
    holdings = [make_holding_analysis(symbol="A", unavailable=True)]
    result = PortfolioScore().compute(_diversification(), _risk(), _cash(), holdings)
    assert result.components["recommendation_alignment"] == 50.0
