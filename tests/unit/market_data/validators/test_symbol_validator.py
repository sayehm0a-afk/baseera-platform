"""Unit tests for per-market symbol format validation (Tadawul + US,
product decision 2026-09-18 multi-market expansion Phase 1)."""

import pytest

from src.domain.models.stock import Market
from src.market_data.validators.symbol_validator import (
    InvalidSymbolError,
    is_valid_symbol_format,
    validate_symbol_format,
)


@pytest.mark.parametrize("symbol", ["1120", "2222", "0001", "9999"])
def test_is_valid_symbol_format_accepts_four_digit_codes(symbol):
    assert is_valid_symbol_format(symbol) is True


@pytest.mark.parametrize(
    "symbol", ["AAPL", "112", "11200", "112a", "", None, 1120, "  1120", "1120 "]
)
def test_is_valid_symbol_format_rejects_non_matching_input(symbol):
    assert is_valid_symbol_format(symbol) is False


def test_validate_symbol_format_passes_silently_for_valid_symbol():
    validate_symbol_format("1120")  # must not raise


def test_validate_symbol_format_raises_invalid_symbol_error():
    with pytest.raises(InvalidSymbolError, match="1120"):
        validate_symbol_format("AAPL")


# --- US market (product decision 2026-09-18) -------------------------


@pytest.mark.parametrize("symbol", ["AAPL", "TSLA", "F", "GOOGL", "BRK"])
def test_is_valid_symbol_format_accepts_real_us_tickers(symbol):
    assert is_valid_symbol_format(symbol, market=Market.US) is True


@pytest.mark.parametrize(
    "symbol", ["aapl", "1120", "TOOLONG", "", None, "AA PL", "AA-PL"]
)
def test_is_valid_symbol_format_rejects_non_us_tickers(symbol):
    assert is_valid_symbol_format(symbol, market=Market.US) is False


def test_a_real_tadawul_symbol_is_never_valid_as_a_us_ticker_and_vice_versa():
    """The two markets' formats never overlap -- a 4-digit Tadawul code
    is never mistaken for a US ticker, and a real US ticker never
    accidentally passes Tadawul's own check."""
    assert is_valid_symbol_format("1120", market=Market.US) is False
    assert is_valid_symbol_format("AAPL", market=Market.TADAWUL) is False


def test_validate_symbol_format_passes_silently_for_a_valid_us_ticker():
    validate_symbol_format("AAPL", market=Market.US)  # must not raise


def test_validate_symbol_format_raises_for_an_invalid_us_ticker():
    with pytest.raises(InvalidSymbolError, match="AAPL"):
        validate_symbol_format("1120", market=Market.US)


def test_default_market_is_tadawul_for_every_existing_call_site():
    """Every call site written before this change (client.py, stocks.py,
    watchlist.py) calls these functions with no market argument -- their
    exact prior behavior must be unchanged."""
    assert is_valid_symbol_format("1120") is True
    assert is_valid_symbol_format("AAPL") is False
