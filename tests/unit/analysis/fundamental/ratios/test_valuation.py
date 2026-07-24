"""Unit tests for src.analysis.fundamental.ratios.valuation."""

from datetime import date

import pytest

from src.analysis.fundamental.ratios.valuation import (
    dividend_yield,
    market_cap,
    price_to_book,
    price_to_earnings,
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


def test_price_to_earnings_reference_value():
    assert price_to_earnings(_facts(), price=15.0) == pytest.approx(50.0)


def test_price_to_book_reference_value():
    # book_value_per_share = 1800/500 = 3.6 -> P/B = 15/3.6
    assert price_to_book(_facts(), price=15.0) == pytest.approx(15 / 3.6)


def test_dividend_yield_reference_value():
    assert dividend_yield(_facts(), price=15.0) == pytest.approx(0.1 / 15)


def test_market_cap_reference_value():
    assert market_cap(_facts(), price=15.0) == pytest.approx(7500.0)


def test_price_to_earnings_none_when_price_missing():
    assert price_to_earnings(_facts(), price=None) is None


def test_price_to_earnings_none_on_zero_eps():
    assert price_to_earnings(_facts(eps=0.0), price=15.0) is None


def test_price_to_book_none_when_price_missing():
    assert price_to_book(_facts(), price=None) is None


def test_price_to_book_none_on_zero_shares_outstanding():
    assert price_to_book(_facts(shares_outstanding=0), price=15.0) is None


def test_dividend_yield_none_when_price_missing():
    assert dividend_yield(_facts(), price=None) is None


def test_dividend_yield_none_on_zero_price():
    assert dividend_yield(_facts(), price=0.0) is None


def test_market_cap_none_when_price_missing():
    assert market_cap(_facts(), price=None) is None
