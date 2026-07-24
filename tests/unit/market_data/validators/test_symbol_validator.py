"""Unit tests for Tadawul symbol format/known-symbol validation.

No conftest.py exists anywhere in this repository, by design (see
tests/integration/api/_helpers.py's own note) -- so the in-memory
SQLite session used by the is_known_symbol/validate_known_symbol tests
is built directly in this module, mirroring the same
check_same_thread=False + StaticPool pattern already established in
tests/integration/api/_helpers.py.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import Stock
from src.market_data.validators.symbol_validator import (
    InvalidSymbolError,
    is_known_symbol,
    is_valid_symbol_format,
    validate_known_symbol,
    validate_symbol_format,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@pytest.mark.parametrize("symbol", ["1120", "1010", "2222", "0001"])
def test_is_valid_symbol_format_accepts_four_digits(symbol):
    assert is_valid_symbol_format(symbol) is True


@pytest.mark.parametrize(
    "symbol",
    ["AAPL", "11200", "111", "abcd", "", "112a", None, 1120],
)
def test_is_valid_symbol_format_rejects_non_four_digit_strings(symbol):
    assert is_valid_symbol_format(symbol) is False


def test_validate_symbol_format_raises_for_malformed_symbol():
    with pytest.raises(InvalidSymbolError):
        validate_symbol_format("AAPL")


def test_validate_symbol_format_does_not_raise_for_valid_symbol():
    validate_symbol_format("1120")  # must not raise


def test_is_known_symbol_true_when_row_exists(session):
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank"))
    session.commit()
    assert is_known_symbol(session, "1120") is True


def test_is_known_symbol_false_when_row_absent(session):
    assert is_known_symbol(session, "9999") is False


def test_validate_known_symbol_raises_for_malformed_symbol(session):
    with pytest.raises(InvalidSymbolError):
        validate_known_symbol(session, "AAPL")


def test_validate_known_symbol_raises_for_well_formed_but_unlisted_symbol(session):
    with pytest.raises(InvalidSymbolError):
        validate_known_symbol(session, "9999")


def test_validate_known_symbol_does_not_raise_for_known_symbol(session):
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank"))
    session.commit()
    validate_known_symbol(session, "1120")  # must not raise
