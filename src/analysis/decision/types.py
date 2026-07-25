"""Shared types for the AI Decision Intelligence Layer.

This layer sits above TechnicalAnalysisEngine, FundamentalAnalysisEngine,
and RecommendationEngine (which already includes confidence scoring --
see its own module docstring): `AIDecisionEngine` calls
`RecommendationEngine.generate()` as a black box and adds what none of
those layers produce -- a target price, a stop loss, a time horizon, an
expected return, a risk level, a position-size recommendation, and a
list of plain-language reasons. It reuses `RecommendationEngine`'s own
`ScoreContributor` extension point (see src/analysis/recommendation/
types.py) rather than inventing a parallel one: every new module this
layer adds (Momentum, Volume, Risk, News, Macro, Insider Transactions,
Sector Rotation) is just one more `ScoreContributor` in the list passed
to `RecommendationEngine`, so `RecommendationEngine`/`ScoreContributor`
themselves need zero changes.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from src.analysis.recommendation.types import Recommendation, Signal


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class TimeHorizon(str, Enum):
    SHORT_TERM = "SHORT_TERM"  # days to a few weeks
    MEDIUM_TERM = "MEDIUM_TERM"  # weeks to a few months
    LONG_TERM = "LONG_TERM"  # months and beyond


class PositionSize(str, Enum):
    NONE = "NONE"
    SMALL = "SMALL"
    MODERATE = "MODERATE"
    STANDARD = "STANDARD"
    LARGE = "LARGE"


@dataclass(frozen=True)
class DecisionFactorBreakdown:
    """One line of the explainable breakdown -- "Technical Analysis:
    +35", "Risk: -6", etc. `points` is signed and centered on 0 (a
    contributor's 0-100 score minus its 50-point neutral baseline),
    exactly the shape the breakdown is meant to display."""

    category: str
    points: float
    weight: float
    confidence: float
    available: bool
    notes: Optional[str] = None


@dataclass(frozen=True)
class InvestmentDecision:
    """The AI Decision Intelligence Layer's final output for one
    symbol: everything RecommendationEngine already produces
    (recommendation, confidence, final_score, signals), plus what only
    this layer computes."""

    symbol: str
    recommendation: Recommendation
    confidence: float
    final_score: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    time_horizon: TimeHorizon
    expected_return_pct: Optional[float]
    risk_level: RiskLevel
    position_size: PositionSize
    reasons: List[str]
    breakdown: List[DecisionFactorBreakdown]
    signals: List[Signal]
    generated_at: datetime
