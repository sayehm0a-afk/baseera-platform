"""Unit tests for src.analysis.fundamental.ratios.leverage."""

from datetime import date

import pytest

from src.analysis.fundamental.ratios.leverage import (
    debt_to_assets,
    debt_to_equity,
    equity_multiplier,
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


def test_debt_to_equity_reference_value():
    assert debt_to_equity(_facts()) == pytest.approx(500 / 1800)


def test_debt_to_assets_reference_value():
    assert debt_to_assets(_facts()) == pytest.approx(500 / 3000)


def test_equity_multiplier_reference_value():
    assert equity_multiplier(_facts()) == pytest.approx(3000 / 1800)


def test_debt_to_equity_none_when_debt_missing():
    assert debt_to_equity(_facts(total_debt=None)) is None


def test_debt_to_equity_none_on_zero_equity():
    assert debt_to_equity(_facts(total_equity=0.0)) is None


def test_debt_to_assets_none_when_debt_missing():
    assert debt_to_assets(_facts(total_debt=None)) is None


def test_debt_to_assets_none_on_zero_assets():
    assert debt_to_assets(_facts(total_assets=0.0)) is None


def test_equity_multiplier_none_on_zero_equity():
    assert equity_multiplier(_facts(total_equity=0.0)) is None
