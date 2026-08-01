"""Shared types for the Autonomous Market Intelligence Layer.

This layer is an *aggregation* layer, not a sixth analysis/decision
engine: it never computes an indicator, a ratio, a score, or a
narrative itself -- every number and every sentence in a
`SymbolScanOutcome` comes from `AnalystEngine.analyze()` (Phase 6),
which itself reuses `AIDecisionEngine` -> `RecommendationEngine` ->
`TechnicalAnalysisEngine`/`FundamentalAnalysisEngine` (Phases 2-5)
unmodified. This module's only job is defining the shapes that let
many symbols' already-computed `AnalystReport`s be ranked, grouped,
diffed, and watched.

`SymbolScanOutcome` additionally carries `technical_snapshot`/
`fundamental_snapshot` -- both produced by calling `.latest_snapshot()`
on the same `TechnicalAnalysisResult`/`FundamentalAnalysisResult`
`build_analysis_context()` already computed for this symbol's
`AnalystReport` (see `TechnicalAnalysisResult.latest_snapshot()`'s own
docstring: "the shape a future Signal Engine / Confidence Scoring / AI
Decision Layer consumes as input" -- this layer is exactly such a
consumer). No indicator or ratio is recomputed to populate them.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.analysis.analyst.types import AnalystReport
from src.analysis.decision.ai_decision_engine import CATEGORY_LABELS
from src.analysis.decision.types import PositionSize, RiskLevel, TimeHorizon
from src.analysis.recommendation.types import AnalysisContext, Recommendation


class RankingCategory(str, Enum):
    TOP_BUY = "TOP_BUY"
    TOP_STRONG_BUY = "TOP_STRONG_BUY"
    TOP_LONG_TERM_INVESTMENT = "TOP_LONG_TERM_INVESTMENT"
    TOP_SWING_TRADE = "TOP_SWING_TRADE"
    TOP_DIVIDEND_STOCKS = "TOP_DIVIDEND_STOCKS"
    HIGHEST_CONFIDENCE = "HIGHEST_CONFIDENCE"
    HIGHEST_EXPECTED_RETURN = "HIGHEST_EXPECTED_RETURN"
    LOWEST_RISK = "LOWEST_RISK"
    HIGHEST_RISK = "HIGHEST_RISK"
    MOST_BULLISH = "MOST_BULLISH"
    MOST_BEARISH = "MOST_BEARISH"
    MOST_IMPROVED_TODAY = "MOST_IMPROVED_TODAY"
    MOST_DETERIORATED_TODAY = "MOST_DETERIORATED_TODAY"
    NEW_OPPORTUNITIES = "NEW_OPPORTUNITIES"
    REMOVED_OPPORTUNITIES = "REMOVED_OPPORTUNITIES"
    RECENTLY_UPGRADED = "RECENTLY_UPGRADED"
    RECENTLY_DOWNGRADED = "RECENTLY_DOWNGRADED"


class WatchlistCategory(str, Enum):
    MOMENTUM = "MOMENTUM"
    INVESTMENT = "INVESTMENT"
    SWING = "SWING"
    HIGH_RISK = "HIGH_RISK"
    DIVIDEND = "DIVIDEND"
    RECOVERY = "RECOVERY"
    BREAKOUT_CANDIDATES = "BREAKOUT_CANDIDATES"
    OVERSOLD_OPPORTUNITIES = "OVERSOLD_OPPORTUNITIES"
    OVERBOUGHT_WARNINGS = "OVERBOUGHT_WARNINGS"


class ChangeType(str, Enum):
    RECOMMENDATION_CHANGE = "RECOMMENDATION_CHANGE"
    CONFIDENCE_CHANGE = "CONFIDENCE_CHANGE"
    SCORE_CHANGE = "SCORE_CHANGE"
    TARGET_PRICE_CHANGE = "TARGET_PRICE_CHANGE"
    RISK_CHANGE = "RISK_CHANGE"
    TECHNICAL_CHANGE = "TECHNICAL_CHANGE"
    FUNDAMENTAL_CHANGE = "FUNDAMENTAL_CHANGE"


class AlertType(str, Enum):
    NEW_STRONG_BUY = "NEW_STRONG_BUY"
    RECOMMENDATION_UPGRADED = "RECOMMENDATION_UPGRADED"
    RECOMMENDATION_DOWNGRADED = "RECOMMENDATION_DOWNGRADED"
    CONFIDENCE_ABOVE_THRESHOLD = "CONFIDENCE_ABOVE_THRESHOLD"
    TARGET_REACHED = "TARGET_REACHED"
    RISK_SPIKE = "RISK_SPIKE"
    SECTOR_ROTATION = "SECTOR_ROTATION"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ScheduleInterval(str, Enum):
    EVERY_MINUTE = "EVERY_MINUTE"
    EVERY_5_MINUTES = "EVERY_5_MINUTES"
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class PublicationStatus(str, Enum):
    """Whether one symbol's already-computed recommendation may be
    surfaced as a real opportunity -- see publication_gate.py. A
    recommendation existing (`SymbolScanOutcome.report` is not None)
    is not the same as it being *publishable*; ranking.py's "top
    opportunity" categories must only ever contain PUBLISHED entries."""

    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    WATCH_ONLY = "WATCH_ONLY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    detail: str


@dataclass(frozen=True)
class PublicationEvaluation:
    status: PublicationStatus
    gates: List[GateResult]
    disclosures: List[str]


@dataclass(frozen=True)
class SymbolScanOutcome:
    """One symbol's result from one market scan.

    `report` is `None` whenever the symbol was skipped (no technical
    AND no fundamental data -- the same "insufficient data" condition
    `/analyst-report` returns a 422 for, here simply omitted from the
    scan rather than failing it) or failed with an unexpected error
    (`error` set, `success=False`). A `report` present with
    `success=True` is the only state every downstream ranking/
    watchlist/sector rule may read from.
    """

    symbol: str
    sector: Optional[str]
    success: bool
    report: Optional[AnalystReport]
    skipped_reason: Optional[str] = None
    error: Optional[str] = None
    latest_price: Optional[float] = None
    technical_snapshot: Optional[Dict[str, Any]] = None
    fundamental_snapshot: Optional[Dict[str, Any]] = None
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # E8 of the AI Evolution Layer: the exact `AnalysisContext`
    # `build_analysis_context()` computed for this symbol, carried
    # through so a paper-trading challenger engine can re-score it
    # under a different calibration config without a second fetch.
    # Not persisted anywhere -- purely an in-process handoff from
    # `MarketScanner` to `MarketIntelligenceRepository.save_symbol_records`.
    context: Optional[AnalysisContext] = None

    @property
    def recommendation(self) -> Optional[Recommendation]:
        return self.report.decision.recommendation if self.report else None

    @property
    def confidence(self) -> Optional[float]:
        return self.report.decision.confidence if self.report else None

    @property
    def final_score(self) -> Optional[float]:
        return self.report.decision.final_score if self.report else None

    @property
    def target_price(self) -> Optional[float]:
        return self.report.decision.target_price if self.report else None

    @property
    def stop_loss(self) -> Optional[float]:
        return self.report.decision.stop_loss if self.report else None

    @property
    def expected_return_pct(self) -> Optional[float]:
        return self.report.decision.expected_return_pct if self.report else None

    @property
    def risk_level(self) -> Optional[RiskLevel]:
        return self.report.decision.risk_level if self.report else None

    @property
    def risk_reward_ratio(self) -> Optional[float]:
        return self.report.decision.risk_reward_ratio if self.report else None

    @property
    def time_horizon(self) -> Optional[TimeHorizon]:
        return self.report.decision.time_horizon if self.report else None

    @property
    def position_size(self) -> Optional[PositionSize]:
        return self.report.decision.position_size if self.report else None

    def category_score(self, category: str) -> Optional[float]:
        """A contributor category's 0-100 score, reconstructed from
        `DecisionFactorBreakdown.points` (signed, centered on 0) --
        never recomputed."""
        if self.report is None:
            return None
        for breakdown in self.report.decision.breakdown:
            if breakdown.category == category and breakdown.available:
                return round(breakdown.points + 50.0, 2)
        return None

    @property
    def technical_score(self) -> Optional[float]:
        return self.category_score(CATEGORY_LABELS["technical"])

    @property
    def fundamental_score(self) -> Optional[float]:
        return self.category_score(CATEGORY_LABELS["fundamental"])

    @property
    def rsi(self) -> Optional[float]:
        return (self.technical_snapshot or {}).get("rsi_14")

    @property
    def adx(self) -> Optional[float]:
        return (self.technical_snapshot or {}).get("adx_14")

    @property
    def bollinger_upper(self) -> Optional[float]:
        bollinger = (self.technical_snapshot or {}).get("bollinger")
        return bollinger.get("upper") if isinstance(bollinger, dict) else None

    @property
    def dividend_yield(self) -> Optional[float]:
        return (self.fundamental_snapshot or {}).get("dividend_yield")

    @property
    def average_volume(self) -> Optional[float]:
        """20-period average share volume, from the same volume_sma_20
        indicator TechnicalAnalysisEngine already computes -- no new
        calculation. None when the indicator wasn't computed (e.g.
        insufficient history), never defaulted to 0."""
        return (self.technical_snapshot or {}).get("volume_sma_20")

    @property
    def average_traded_value(self) -> Optional[float]:
        """Average daily traded value (price x average volume) -- the
        liquidity proxy publication_gate.py's liquidity gate reads.
        None when either input is unavailable."""
        if self.latest_price is None or self.average_volume is None:
            return None
        return self.latest_price * self.average_volume


@dataclass(frozen=True)
class MarketScanSummary:
    total_requested: int
    total_succeeded: int
    total_skipped: int
    total_failed: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float


@dataclass(frozen=True)
class RankingEntry:
    symbol: str
    sector: Optional[str]
    recommendation: Optional[str]
    confidence: Optional[float]
    final_score: Optional[float]
    target_price: Optional[float]
    expected_return_pct: Optional[float]
    risk_level: Optional[str]
    rank_value: Optional[float]


@dataclass(frozen=True)
class RankingList:
    category: RankingCategory
    entries: List[RankingEntry]
    generated_at: datetime


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    sector: Optional[str]
    recommendation: Optional[str]
    confidence: Optional[float]
    reason: str


@dataclass(frozen=True)
class WatchlistResult:
    category: WatchlistCategory
    entries: List[WatchlistEntry]
    generated_at: datetime


@dataclass(frozen=True)
class SectorSummary:
    sector: str
    symbol_count: int
    average_confidence: Optional[float]
    average_final_score: Optional[float]
    average_expected_return_pct: Optional[float]
    average_technical_score: Optional[float]
    average_fundamental_score: Optional[float]
    buy_count: int
    sell_count: int
    hold_count: int
    breadth: float  # fraction (0..1) of scanned symbols in this sector rated BUY/STRONG_BUY
    momentum: Optional[float] = None  # average_final_score delta vs the previous scan; None on a symbol's/sector's first scan


@dataclass(frozen=True)
class ChangeEvent:
    symbol: str
    change_type: ChangeType
    previous_value: Optional[str]
    new_value: Optional[str]
    delta: Optional[float]
    detected_at: datetime


@dataclass(frozen=True)
class ChangeDetectionResult:
    """`ChangeDetector.detect()`'s full output: the diff events plus
    the two symbol-set deltas (`new_symbols`/`removed_symbols`)
    ranking categories like NEW_OPPORTUNITIES need but that aren't
    expressible as a single symbol's before/after value pair."""

    events: List[ChangeEvent]
    new_symbols: List[str]
    removed_symbols: List[str]
    previous_scan_run_id: Optional[int]


@dataclass(frozen=True)
class Alert:
    alert_type: AlertType
    severity: AlertSeverity
    symbol: Optional[str]
    sector: Optional[str]
    message: str
    generated_at: datetime


@dataclass(frozen=True)
class MarketSnapshotData:
    generated_at: datetime
    symbols_scanned: int
    bull_bear_ratio: Optional[float]
    average_confidence: Optional[float]
    average_recommendation_score: Optional[float]
    buy_signal_count: int
    sell_signal_count: int
    strongest_sectors: List[str]
    weakest_sectors: List[str]
    most_important_changes: List[ChangeEvent]
