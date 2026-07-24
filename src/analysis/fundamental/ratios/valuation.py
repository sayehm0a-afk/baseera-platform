"""Valuation ratios: P/E, P/B, dividend yield, market cap.

The only ratio category that needs a market price -- deliberately not
stored on FundamentalSnapshot (see that model's docstring), so every
function here takes `price` as an explicit parameter, sourced by the
caller from src.analysis.ohlcv_loader's latest close. None (never
raises) when price is unavailable or a denominator is zero.
"""

from typing import Optional

from src.analysis.fundamental.types import FundamentalFacts


def price_to_earnings(facts: FundamentalFacts, price: Optional[float]) -> Optional[float]:
    if price is None or facts.eps == 0:
        return None
    return price / facts.eps


def price_to_book(facts: FundamentalFacts, price: Optional[float]) -> Optional[float]:
    if price is None or facts.shares_outstanding == 0:
        return None
    book_value_per_share = facts.total_equity / facts.shares_outstanding
    if book_value_per_share == 0:
        return None
    return price / book_value_per_share


def dividend_yield(facts: FundamentalFacts, price: Optional[float]) -> Optional[float]:
    if price is None or price == 0:
        return None
    return facts.dividend_per_share / price


def market_cap(facts: FundamentalFacts, price: Optional[float]) -> Optional[float]:
    if price is None:
        return None
    return price * facts.shares_outstanding
