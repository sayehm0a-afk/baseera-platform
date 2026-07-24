"""Profitability ratios: net profit margin, gross profit margin,
return on equity (ROE), return on assets (ROA).

Pure computation over a FundamentalFacts instance -- no I/O, no
database. Every function returns None (never raises) when its inputs
are missing or its denominator is zero -- see types.py's RatioOutput
docstring for why that is the correct behavior here, unlike the
OHLCV-based technical indicators.
"""

from typing import Optional

from src.analysis.fundamental.types import FundamentalFacts


def net_profit_margin(facts: FundamentalFacts) -> Optional[float]:
    if facts.revenue == 0:
        return None
    return facts.net_income / facts.revenue


def gross_profit_margin(facts: FundamentalFacts) -> Optional[float]:
    if facts.gross_profit is None or facts.revenue == 0:
        return None
    return facts.gross_profit / facts.revenue


def return_on_equity(facts: FundamentalFacts) -> Optional[float]:
    if facts.total_equity == 0:
        return None
    return facts.net_income / facts.total_equity


def return_on_assets(facts: FundamentalFacts) -> Optional[float]:
    if facts.total_assets == 0:
        return None
    return facts.net_income / facts.total_assets
