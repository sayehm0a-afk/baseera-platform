"""Unit tests for src.analysis.fundamental.ratios.profitability."""

from datetime import date

import pytest

from src.analysis.fundamental.ratios.profitability import (
    gross_profit_margin,
    net_profit_margin,
    return_on_assets,
    return_on_equity,
)
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


def test_net_profit_margin_reference_value():
    assert net_profit_margin(_facts()) == pytest.approx(0.15)


def test_gross_profit_margin_reference_value():
    assert gross_profit_margin(_facts()) == pytest.approx(0.4)


def test_return_on_equity_reference_value():
    assert return_on_equity(_facts()) == pytest.approx(150 / 1800)


def test_return_on_assets_reference_value():
    assert return_on_assets(_facts()) == pytest.approx(0.05)


def test_net_profit_margin_none_on_zero_revenue():
    assert net_profit_margin(_facts(revenue=0.0)) is None


def test_gross_profit_margin_none_when_gross_profit_missing():
    assert gross_profit_margin(_facts(gross_profit=None)) is None


def test_gross_profit_margin_none_on_zero_revenue():
    assert gross_profit_margin(_facts(revenue=0.0)) is None


def test_return_on_equity_none_on_zero_equity():
    assert return_on_equity(_facts(total_equity=0.0)) is None


def test_return_on_assets_none_on_zero_assets():
    assert return_on_assets(_facts(total_assets=0.0)) is None


def test_return_on_equity_handles_negative_equity():
    # A company with negative equity (accumulated losses) still has a
    # mathematically defined, if unusual, ROE -- not a None case.
    result = return_on_equity(_facts(total_equity=-500.0))
    assert result == pytest.approx(150 / -500)
