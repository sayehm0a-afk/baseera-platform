"""Leverage/solvency ratios: debt-to-equity, debt-to-assets, equity
multiplier.

Pure computation over a FundamentalFacts instance -- no I/O, no
database. Returns None (never raises) on a zero/missing denominator or
missing required input.
"""

from typing import Optional

from src.analysis.fundamental.types import FundamentalFacts


def debt_to_equity(facts: FundamentalFacts) -> Optional[float]:
    if facts.total_debt is None or facts.total_equity == 0:
        return None
    return facts.total_debt / facts.total_equity


def debt_to_assets(facts: FundamentalFacts) -> Optional[float]:
    if facts.total_debt is None or facts.total_assets == 0:
        return None
    return facts.total_debt / facts.total_assets


def equity_multiplier(facts: FundamentalFacts) -> Optional[float]:
    if facts.total_equity == 0:
        return None
    return facts.total_assets / facts.total_equity
