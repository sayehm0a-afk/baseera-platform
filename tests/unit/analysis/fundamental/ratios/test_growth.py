"""Unit tests for src.analysis.fundamental.ratios.growth."""

from datetime import date

import pytest

from src.analysis.fundamental.ratios.growth import eps_growth, net_income_growth, revenue_growth
from src.analysis.fundamental.types import FundamentalFacts


def _facts(**overrides) -> FundamentalFacts:
    defaults = dict(
        stock_id=1,
        period_type="annual",
        fiscal_period_end=date(2024, 12, 31),
        revenue=1000.0,
        gross_profit=400.0,
        net_income=150.0,
        total_assets=3000.0,
        total_liabilities=1200.0,
        total_equity=1800.0,
        current_assets=700.0,
        current_liabilities=400.0,
        inventory=100.0,
        cash_and_equivalents=200.0,
        total_debt=500.0,
        shares_outstanding=500,
        eps=0.3,
        dividend_per_share=0.1,
    )
    defaults.update(overrides)
    return FundamentalFacts(**defaults)


def _prior(**overrides) -> FundamentalFacts:
    defaults = dict(
        stock_id=1,
        period_type="annual",
        fiscal_period_end=date(2023, 12, 31),
        revenue=800.0,
        gross_profit=300.0,
        net_income=100.0,
        total_assets=2800.0,
        total_liabilities=1200.0,
        total_equity=1600.0,
        current_assets=650.0,
        current_liabilities=380.0,
        inventory=90.0,
        cash_and_equivalents=180.0,
        total_debt=480.0,
        shares_outstanding=500,
        eps=0.2,
        dividend_per_share=0.08,
    )
    defaults.update(overrides)
    return FundamentalFacts(**defaults)


def test_revenue_growth_reference_value():
    assert revenue_growth(_facts(), _prior()) == pytest.approx(0.25)


def test_net_income_growth_reference_value():
    assert net_income_growth(_facts(), _prior()) == pytest.approx(0.5)


def test_eps_growth_reference_value():
    assert eps_growth(_facts(), _prior()) == pytest.approx(0.5)


def test_revenue_growth_none_when_no_prior_period():
    assert revenue_growth(_facts(), None) is None


def test_net_income_growth_none_when_no_prior_period():
    assert net_income_growth(_facts(), None) is None


def test_eps_growth_none_when_no_prior_period():
    assert eps_growth(_facts(), None) is None


def test_revenue_growth_none_on_zero_prior_revenue():
    assert revenue_growth(_facts(), _prior(revenue=0.0)) is None


def test_net_income_growth_none_on_zero_prior_net_income():
    assert net_income_growth(_facts(), _prior(net_income=0.0)) is None


def test_eps_growth_none_on_zero_prior_eps():
    assert eps_growth(_facts(), _prior(eps=0.0)) is None


def test_revenue_growth_handles_decline():
    result = revenue_growth(_facts(revenue=600.0), _prior())
    assert result == pytest.approx((600 - 800) / 800)
