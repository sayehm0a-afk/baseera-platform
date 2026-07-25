"""Shared types for the Recommendation & Confidence Engine.

This engine is an *orchestration* layer, not a third analysis engine:
it never computes an indicator or a ratio itself, it only combines the
outputs `TechnicalAnalysisEngine` (M2.2) and `FundamentalAnalysisEngine`
(M2.3) already produced. Neither engine is imported for anything other
than its already-public result types (TechnicalAnalysisResult,
FundamentalAnalysisResult) -- nothing about either engine changes here.

The extension point is `ScoreContributor`: a small protocol any module
(technical, fundamental, and later news sentiment, insider trades,
macro indicators, an AI reasoning layer, ...) can implement to plug
into `RecommendationEngine` without that engine's public
`generate(context) -> RecommendationResult` signature ever changing.
A future module that needs raw data neither `AnalysisContext` field
already carries can read it from `AnalysisContext.extra`, a free-form
bag keyed by convention -- so adding a module never requires editing
this dataclass either.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult


class Recommendation(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class SignalDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class Signal:
    """One human-readable observation a contributor based its score on.

    `impact` is the number of points (positive or negative, on the same
    0-100 scale as ScoreContribution.score, centered on a 50-point
    neutral baseline) this specific signal contributed to its module's
    score -- 0.0 for a purely informational signal (e.g. a volatility
    note) that didn't move the score. It is what lets the engine pick
    "the signals that actually drove this recommendation" for the
    explanation, rather than dumping every observation undifferentiated.
    """

    name: str
    description: str
    direction: SignalDirection
    source: str
    impact: float = 0.0


@dataclass(frozen=True)
class ScoreContribution:
    """One module's opinion: a 0-100 bullishness score (50 = neutral),
    how much weight it should carry in the final blend, how confident
    the module itself is in that score, and the signals behind it.

    `score`/`weight` are both `None`/`0.0` when the module had nothing
    to work with (e.g. no fundamentals have been ingested yet for this
    symbol) -- a disclosed "this module sat out," not an error, exactly
    the same honesty-by-omission discipline `RatioOutput.value=None`
    already uses for an individual ratio.
    """

    source: str
    score: Optional[float]
    weight: float
    confidence: float
    signals: List[Signal] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass(frozen=True)
class AnalysisContext:
    """Everything available to compute a recommendation for one symbol.

    `technical_result`/`fundamental_result` are `None`, not omitted,
    when that engine could not run (insufficient history / no ingested
    fundamentals) -- contributors are required to handle `None`
    gracefully and report themselves as unavailable, never raise.

    `latest_price` is optional and additive (added for the AI Decision
    Intelligence Layer's target price/stop loss calculations,
    src/analysis/decision/) -- existing contributors that don't need a
    price anchor simply never read it.
    """

    symbol: str
    technical_result: Optional[TechnicalAnalysisResult] = None
    fundamental_result: Optional[FundamentalAnalysisResult] = None
    latest_price: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ScoreContributor(Protocol):
    """The one interface every scoring module (technical, fundamental,
    and any future module) implements. `RecommendationEngine` depends
    only on this shape -- adding a module means writing a class that
    satisfies it and passing an instance into the engine's contributor
    list, nothing else changes."""

    name: str
    default_weight: float

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        ...


@dataclass(frozen=True)
class RecommendationTuning:
    """Every numeric constant `RecommendationEngine.generate()` would
    otherwise hardcode -- recommendation-band thresholds and the
    confidence agreement/disagreement heuristic. Field defaults are
    exactly the values RecommendationEngine used before this dataclass
    existed, so `RecommendationEngine(contributors=[...])` (no
    `tuning=`) behaves identically to before -- this exists purely so
    the Backtesting & Calibration Engine (src/backtesting/) can
    propose and evaluate alternative values without editing this
    engine's code, the same reasoning `ScoreContributor` already
    applies to *which modules* run, now applied to *how their blended
    score becomes a recommendation*.
    """

    strong_buy_threshold: float = 75.0
    buy_threshold: float = 60.0
    sell_threshold: float = 40.0
    strong_sell_threshold: float = 25.0
    agreement_spread_threshold: float = 15.0
    agreement_bonus: float = 8.0
    disagreement_spread_threshold: float = 40.0
    disagreement_penalty: float = 12.0
    # confidence = weighted_confidence * (coverage ** this) -- 1.0 (the
    # default) is the original linear "missing modules proportionally
    # reduce confidence" behavior; >1.0 penalizes missing data more
    # harshly, <1.0 more gently. Calibratable per Phase 5's "confidence
    # penalties for missing data."
    coverage_penalty_exponent: float = 1.0


@dataclass(frozen=True)
class RecommendationResult:
    """The final, explainable output for one symbol."""

    symbol: str
    recommendation: Recommendation
    confidence: float
    explanation: str
    technical_score: Optional[float]
    fundamental_score: Optional[float]
    final_score: float
    contributions: List[ScoreContribution]
    signals: List[Signal]
    generated_at: datetime
