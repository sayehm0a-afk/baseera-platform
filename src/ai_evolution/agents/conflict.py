"""Decides whether a live recommendation's Technical-vs-Fundamental
evidence disagrees enough to justify running a real (LLM-cost-bearing)
debate. Mirrors `src.analysis.analyst.conflict_resolver`'s exact
tension-level thresholds (30/15/5-point spread) and reasoning -- that
module operates on `Evidence`/`InterpretedSignals` objects built deep
inside `ReasoningPipeline`, which aren't exposed back to the live scan
caller; this reimplements the same thresholds directly against
`InvestmentDecision.breakdown` (a plain `List[DecisionFactorBreakdown]`,
already in scope at the scan call site) rather than reconstructing
those richer objects just to reuse one method.
"""

import enum
from typing import List, Optional

from src.analysis.decision.types import DecisionFactorBreakdown

_TECHNICAL_CATEGORY = "Technical Analysis"
_FUNDAMENTAL_CATEGORY = "Fundamental Analysis"

HIGH_TENSION_THRESHOLD = 30.0
MODERATE_TENSION_THRESHOLD = 15.0
MILD_TENSION_THRESHOLD = 5.0

# Debate only triggers at MODERATE or HIGH tension -- MILD disagreement
# is common and not worth the LLM cost of a full debate + Judge call.
DEBATE_TRIGGER_THRESHOLD = MODERATE_TENSION_THRESHOLD


class TensionLevel(str, enum.Enum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


def _category_points(breakdown: List[DecisionFactorBreakdown], category: str) -> Optional[float]:
    for item in breakdown:
        if item.category == category and item.available:
            return item.points
    return None


def tension_level(breakdown: List[DecisionFactorBreakdown]) -> TensionLevel:
    technical_points = _category_points(breakdown, _TECHNICAL_CATEGORY)
    fundamental_points = _category_points(breakdown, _FUNDAMENTAL_CATEGORY)
    if technical_points is None or fundamental_points is None:
        return TensionLevel.NONE

    spread = abs(technical_points - fundamental_points)
    if spread >= HIGH_TENSION_THRESHOLD:
        return TensionLevel.HIGH
    if spread >= MODERATE_TENSION_THRESHOLD:
        return TensionLevel.MODERATE
    if spread >= MILD_TENSION_THRESHOLD:
        return TensionLevel.MILD
    return TensionLevel.NONE


def should_trigger_debate(breakdown: List[DecisionFactorBreakdown]) -> bool:
    level = tension_level(breakdown)
    order = {TensionLevel.NONE: 0, TensionLevel.MILD: 1, TensionLevel.MODERATE: 2, TensionLevel.HIGH: 3}
    return order[level] >= order[TensionLevel.MODERATE]
