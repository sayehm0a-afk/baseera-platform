"""Efficiency ratio: asset turnover.

Pure computation over a FundamentalFacts instance -- no I/O, no
database. Returns None (never raises) on a zero denominator.
"""

from typing import Optional

from src.analysis.fundamental.types import FundamentalFacts


def asset_turnover(facts: FundamentalFacts) -> Optional[float]:
    if facts.total_assets == 0:
        return None
    return facts.revenue / facts.total_assets
