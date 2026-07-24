"""Unit tests for src.analysis.fundamental.ratios.efficiency."""

from datetime import date

import pytest

from src.analysis.fundamental.ratios.efficiency import asset_turnover
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


def test_asset_turnover_reference_value():
    assert asset_turnover(_facts()) == pytest.approx(1000 / 3000)


def test_asset_turnover_none_on_zero_assets():
    assert asset_turnover(_facts(total_assets=0.0)) is None
