"""Stock symbol format validation, per market (product decision
2026-09-18, multi-market expansion Phase 1).

Tadawul (Saudi Exchange) symbols are a 4-digit numeric code (e.g.
"1111", "2222", "1120" for Al Rajhi Bank) -- Tadawul's own real listing
convention. US-listed symbols (Nasdaq/NYSE) are 1-5 uppercase letters
(e.g. "AAPL", "TSLA", "F", "GOOGL") -- the real, standard US ticker
convention. `market` defaults to `Market.TADAWUL` everywhere so every
call site written before this file supported a second market keeps its
exact prior behavior with no change required at the call site.
"""

import re

from src.domain.models.stock import Market

_TADAWUL_SYMBOL_PATTERN = re.compile(r"^\d{4}$")
_US_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}$")

_PATTERN_BY_MARKET = {
    Market.TADAWUL: _TADAWUL_SYMBOL_PATTERN,
    Market.US: _US_SYMBOL_PATTERN,
}

_FORMAT_DESCRIPTION_BY_MARKET = {
    Market.TADAWUL: "expected exactly 4 digits (e.g. '1120')",
    Market.US: "expected 1-5 uppercase letters (e.g. 'AAPL')",
}


class InvalidSymbolError(ValueError):
    pass


def is_valid_symbol_format(symbol: str, market: Market = Market.TADAWUL) -> bool:
    """True iff `symbol` matches the given market's real listing
    convention. Pure format check -- no I/O."""
    if not isinstance(symbol, str):
        return False
    return bool(_PATTERN_BY_MARKET[market].match(symbol))


def validate_symbol_format(symbol: str, market: Market = Market.TADAWUL) -> None:
    """Raises InvalidSymbolError with a disclosed reason if `symbol`
    does not match the given market's real listing convention."""
    if not is_valid_symbol_format(symbol, market):
        raise InvalidSymbolError(
            f"'{symbol}' is not a valid {market.value} symbol: {_FORMAT_DESCRIPTION_BY_MARKET[market]}"
        )
