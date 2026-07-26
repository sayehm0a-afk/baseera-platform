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

from dataclasses import dataclass, field
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


class EntryQuality(str, Enum):
    """How favorable *right now* is as an entry price for the
    recommended direction -- distinct from the recommendation itself
    (a STRONG_BUY can still be a POOR entry if price has already run
    up to just under a resistance level; better to wait for a pullback
    to support). Derived entirely from PriceStructureScoreContributor's
    same inputs (support/resistance, Fibonacci) plus ValueAreaScoreContributor's
    (VWAP, Volume Profile) -- never a new computation of its own."""

    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"


@dataclass(frozen=True)
class AIDecisionTuning:
    """Every numeric constant `AIDecisionEngine` would otherwise
    hardcode -- ATR stop/reward multiples and risk-level thresholds.
    Field defaults exactly reproduce the values AIDecisionEngine used
    before this dataclass existed, so `AIDecisionEngine()` (no
    `tuning=`) behaves identically to before -- the same additive,
    backward-compatible pattern `RecommendationTuning` already applies
    to RecommendationEngine, giving the Backtesting & Calibration
    Engine (src/backtesting/) a way to propose alternative values
    without editing this engine's code.
    """

    stop_atr_multiple: float = 1.5
    base_reward_atr_multiple: float = 2.0
    max_extra_reward_atr_multiple: float = 2.0
    risk_low_threshold: float = 65.0
    risk_medium_threshold: float = 45.0
    risk_high_threshold: float = 25.0
    time_horizon_long_conviction_threshold: float = 25.0
    time_horizon_long_adx_threshold: float = 25.0
    time_horizon_medium_conviction_threshold: float = 10.0

    # Phase 11: price-structure-aware entry/time-horizon/confidence/
    # position-size tuning -- see AIDecisionEngine's _derive_entry_quality,
    # _derive_time_horizon, _calibrate_confidence, _derive_position_size.
    key_level_proximity_threshold: float = 0.015  # 1.5% of price, matches PriceStructureScoreContributor
    entry_quality_excellent_threshold: float = 70.0
    entry_quality_good_threshold: float = 55.0
    entry_quality_fair_threshold: float = 40.0
    poor_risk_reward_threshold: float = 1.0
    excellent_risk_reward_threshold: float = 2.0
    vwap_confidence_adjustment: float = 3.0
    liquidity_confidence_adjustment: float = 3.0
    liquidity_thin_zone_ratio: float = 0.5  # a price bin below this fraction of the average bin is "thin"
    liquidity_thick_zone_ratio: float = 1.2  # a price bin above this fraction of the average bin is "liquid"


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

    # Phase 11: price-structure-driven fields. Defaulted (not required)
    # so the handful of call sites that reconstruct an InvestmentDecision
    # from data that never had these computed -- src/market_intelligence/
    # read_model.py rebuilding from a persisted RecommendationSnapshot
    # whose schema predates them, and test fixtures -- keep working
    # unchanged; AIDecisionEngine.decide() itself always passes real,
    # computed values, never relies on these defaults.
    entry_quality: EntryQuality = EntryQuality.FAIR
    entry_quality_notes: List[str] = field(default_factory=list)
    risk_reward_ratio: Optional[float] = None
    stop_loss_basis: str = "atr"
    target_price_basis: str = "atr"
    confidence_calibration_notes: List[str] = field(default_factory=list)
