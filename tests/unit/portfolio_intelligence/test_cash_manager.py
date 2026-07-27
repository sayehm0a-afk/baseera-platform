"""Unit tests for CashManager."""

from datetime import datetime, timezone

from src.analysis.decision.types import RiskLevel
from src.portfolio_intelligence.cash_manager import CashManager
from src.portfolio_intelligence.types import AllocationBreakdown, PortfolioRiskProfile

_NOW = datetime.now(timezone.utc)


def _risk_profile(risk_level=RiskLevel.MEDIUM):
    return PortfolioRiskProfile(
        risk_score=50.0, risk_level=risk_level, expected_volatility_annualized_pct=15.0,
        estimated_max_drawdown_pct=10.0, portfolio_beta=None, beta_unavailable_reason="n/a",
        correlation_matrix=None, excluded_from_volatility=[], narrative="",
    )


def _allocation(cash, total_value):
    return AllocationBreakdown(entries=[], cash=cash, cash_weight=cash / total_value, total_value=total_value, generated_at=_NOW)


def test_cash_within_band(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MIN", "0.05")
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MAX", "0.15")
    recommendation = CashManager().recommend(_allocation(1000, 10000), _risk_profile())
    assert recommendation.is_within_target_band is True


def test_cash_below_band(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MIN", "0.05")
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MAX", "0.15")
    recommendation = CashManager().recommend(_allocation(100, 10000), _risk_profile())
    assert recommendation.is_within_target_band is False
    assert "below" in recommendation.rationale


def test_cash_above_band(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MIN", "0.05")
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MAX", "0.15")
    recommendation = CashManager().recommend(_allocation(3000, 10000), _risk_profile())
    assert recommendation.is_within_target_band is False
    assert "above" in recommendation.rationale


def test_high_risk_widens_the_target_band(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_CASH_TARGET_PCT_MAX", "0.15")
    monkeypatch.setenv("PORTFOLIO_HIGH_RISK_CASH_TARGET_PCT_MAX", "0.30")
    # 20% cash: outside the normal 15% max, inside the widened 30% max for high risk.
    recommendation_normal = CashManager().recommend(_allocation(2000, 10000), _risk_profile(RiskLevel.MEDIUM))
    recommendation_high_risk = CashManager().recommend(_allocation(2000, 10000), _risk_profile(RiskLevel.VERY_HIGH))
    assert recommendation_normal.is_within_target_band is False
    assert recommendation_high_risk.is_within_target_band is True
    assert recommendation_high_risk.recommended_cash_pct_max == 0.30
