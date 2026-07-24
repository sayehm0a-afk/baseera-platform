"""Tadawul (Saudi Exchange) stock symbol validation.

Every symbol already used throughout this codebase (test fixtures,
docs, the API layer) is a 4-digit numeric code (e.g. "1111", "2222",
"1120" for Al Rajhi Bank) -- Tadawul's own real listing convention, not
an invented format. This module is the one place that format is
checked, so every caller (the live provider, ingestion, the API layer)
validates against the same rule rather than each re-deriving it.

Deliberately format-only for `is_valid_symbol_format`/
`validate_symbol_format`: this does not check whether a symbol is
actually *listed* (that requires a `Stock` row, a call-site concern
this module has no access to without a session) -- see
`is_known_symbol`/`validate_known_symbol` below for the DB-backed
check, kept separate so a caller with no DB session available (e.g. a
provider deciding whether to even attempt a live API call) can still
do the free, local format check alone.
"""

import re

from sqlalchemy.orm import Session

from src.domain.models import Stock

_TADAWUL_SYMBOL_PATTERN = re.compile(r"^\d{4}$")


class InvalidSymbolError(ValueError):
    pass


def is_valid_symbol_format(symbol: str) -> bool:
    """True iff `symbol` matches Tadawul's 4-digit numeric convention.
    Pure format check -- no I/O, no DB, no provider call."""
    return isinstance(symbol, str) and bool(_TADAWUL_SYMBOL_PATTERN.match(symbol))


def validate_symbol_format(symbol: str) -> None:
    """Raises InvalidSymbolError with a disclosed reason if `symbol`
    does not match Tadawul's 4-digit numeric convention. Never raises
    for any other reason (e.g. a genuinely unlisted-but-well-formed
    symbol) -- that is validate_known_symbol's job, not this function's."""
    if not is_valid_symbol_format(symbol):
        raise InvalidSymbolError(
            f"'{symbol}' is not a valid Tadawul symbol: expected exactly 4 digits (e.g. '1120')"
        )


def is_known_symbol(session: Session, symbol: str) -> bool:
    """True iff a Stock row for `symbol` already exists. Requires a DB
    session -- callers without one should use is_valid_symbol_format
    alone."""
    return session.query(Stock).filter(Stock.symbol == symbol).one_or_none() is not None


def validate_known_symbol(session: Session, symbol: str) -> None:
    """Format check, then existence check -- raises InvalidSymbolError
    for either failure, with a distinct, disclosed reason for each."""
    validate_symbol_format(symbol)
    if not is_known_symbol(session, symbol):
        raise InvalidSymbolError(f"'{symbol}' is well-formed but is not a known/listed stock")
