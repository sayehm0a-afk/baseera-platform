"""Unit tests for Tadawul symbol format validation."""

import pytest

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
