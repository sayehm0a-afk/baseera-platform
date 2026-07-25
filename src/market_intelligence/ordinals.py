"""Shared ordinal orderings for `Recommendation`/`RiskLevel` --
`ranking.py` and `alert_engine.py` both need "is this better/worse than
that" comparisons over the same two enums; defined once here so
neither module keeps its own copy.
"""

from src.analysis.decision.types import RiskLevel
from src.analysis.recommendation.types import Recommendation

RECOMMENDATION_RANK = {
    Recommendation.STRONG_SELL: 0,
    Recommendation.SELL: 1,
    Recommendation.HOLD: 2,
    Recommendation.BUY: 3,
    Recommendation.STRONG_BUY: 4,
}

RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.VERY_HIGH: 3,
}


def recommendation_rank_of_value(value) -> int:
    if value is None:
        return -1
    try:
        return RECOMMENDATION_RANK[Recommendation(value)]
    except ValueError:
        return -1


def risk_rank_of_value(value) -> int:
    if value is None:
        return -1
    try:
        return RISK_RANK[RiskLevel(value)]
    except ValueError:
        return -1
