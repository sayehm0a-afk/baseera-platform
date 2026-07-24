"""Unit tests for src.analysis.fundamental.ratios.liquidity."""

from datetime import date

import pytest

from src.analysis.fundamental.ratios.liquidity import cash_ratio, current_ratio, quick_ratio
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


def test_current_ratio_reference_value():
    assert current_ratio(_facts()) == pytest.approx(1.75)


def test_quick_ratio_reference_value():
    assert quick_ratio(_facts()) == pytest.approx(1.5)


def test_cash_ratio_reference_value():
    assert cash_ratio(_facts()) == pytest.approx(0.5)


def test_current_ratio_none_on_zero_current_liabilities():
    assert current_ratio(_facts(current_liabilities=0.0)) is None


def test_quick_ratio_none_on_zero_current_liabilities():
    assert quick_ratio(_facts(current_liabilities=0.0)) is None


def test_cash_ratio_none_on_zero_current_liabilities():
    assert cash_ratio(_facts(current_liabilities=0.0)) is None


def test_quick_ratio_treats_missing_inventory_as_zero():
    result = quick_ratio(_facts(inventory=None))
    assert result == pytest.approx(700 / 400)


def test_cash_ratio_none_when_cash_missing():
    assert cash_ratio(_facts(cash_and_equivalents=None)) is None
