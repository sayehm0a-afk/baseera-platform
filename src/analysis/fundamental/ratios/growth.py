"""Growth ratios: revenue, net income, and EPS period-over-period
growth.

The only ratio category that needs a prior period's FundamentalFacts.
None (never raises) when no prior period is available or the prior
value is zero -- a stock's first-ever reported period has no growth
ratios by definition, not an error condition.
"""

from typing import Optional

from src.analysis.fundamental.types import FundamentalFacts


def revenue_growth(
    facts: FundamentalFacts, prior: Optional[FundamentalFacts]
) -> Optional[float]:
    if prior is None or prior.revenue == 0:
        return None
    return (facts.revenue - prior.revenue) / prior.revenue


def net_income_growth(
    facts: FundamentalFacts, prior: Optional[FundamentalFacts]
) -> Optional[float]:
    if prior is None or prior.net_income == 0:
        return None
    return (facts.net_income - prior.net_income) / prior.net_income


def eps_growth(facts: FundamentalFacts, prior: Optional[FundamentalFacts]) -> Optional[float]:
    if prior is None or prior.eps == 0:
        return None
    return (facts.eps - prior.eps) / prior.eps
