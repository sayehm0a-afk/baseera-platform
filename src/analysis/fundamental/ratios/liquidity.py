"""Liquidity ratios: current ratio, quick ratio, cash ratio.

Pure computation over a FundamentalFacts instance -- no I/O, no
database. Returns None (never raises) on a zero/missing denominator or
missing required input.
"""

from typing import Optional

from src.analysis.fundamental.types import FundamentalFacts


def current_ratio(facts: FundamentalFacts) -> Optional[float]:
    if facts.current_liabilities == 0:
        return None
    return facts.current_assets / facts.current_liabilities


def quick_ratio(facts: FundamentalFacts) -> Optional[float]:
    if facts.current_liabilities == 0:
        return None
    inventory = facts.inventory if facts.inventory is not None else 0.0
    return (facts.current_assets - inventory) / facts.current_liabilities


def cash_ratio(facts: FundamentalFacts) -> Optional[float]:
    if facts.current_liabilities == 0 or facts.cash_and_equivalents is None:
        return None
    return facts.cash_and_equivalents / facts.current_liabilities
