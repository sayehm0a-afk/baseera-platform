"""Tadawul (Saudi Exchange) stock symbol validation.

Every symbol already used throughout this codebase (test fixtures, the
DevMarketDataProvider, domain models) is a 4-digit numeric code (e.g.
"1111", "2222", "1120" for Al Rajhi Bank) -- Tadawul's own real listing
convention. This is the one place that format is checked, so the SAHMK
client and provider validate against the same rule rather than each
re-deriving it, and reject a malformed symbol before spending a
network call on it.
"""

import re

_TADAWUL_SYMBOL_PATTERN = re.compile(r"^\d{4}$")


class InvalidSymbolError(ValueError):
    pass


def is_valid_symbol_format(symbol: str) -> bool:
    """True iff `symbol` matches Tadawul's 4-digit numeric convention.
    Pure format check -- no I/O."""
    return isinstance(symbol, str) and bool(_TADAWUL_SYMBOL_PATTERN.match(symbol))


def validate_symbol_format(symbol: str) -> None:
    """Raises InvalidSymbolError with a disclosed reason if `symbol`
    does not match Tadawul's 4-digit numeric convention."""
    if not is_valid_symbol_format(symbol):
        raise InvalidSymbolError(
            f"'{symbol}' is not a valid Tadawul symbol: expected exactly 4 digits (e.g. '1120')"
        )
