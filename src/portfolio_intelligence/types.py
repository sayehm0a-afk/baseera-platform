"""Shared types for the Autonomous Portfolio Intelligence Layer.

This layer is a *portfolio-level reasoning* layer, not a seventh
analysis/decision engine: it never computes an indicator, a ratio, a
per-symbol score, or a narrative itself -- every per-holding number and
sentence comes from `AnalystEngine.analyze()` (Phase 6), which itself
reuses `AIDecisionEngine` -> `RecommendationEngine` ->
`TechnicalAnalysisEngine`/`FundamentalAnalysisEngine` (Phases 2-5)
unmodified. This module's job is defining the shapes that let many
holdings' already-computed `AnalystReport`s be combined into portfolio-
level allocation, exposure, concentration, diversification, risk,
cash, rebalancing, and health reasoning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.analysis.analyst.types import AnalystReport
from src.analysis.decision.types import PositionSize, RiskLevel


class PositionAction(str, Enum):
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NEW_BUY = "NEW_BUY"


class HealthBand(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Holding:
    """One position as recorded by the portfolio's owner -- pure input
    data, no analysis. `average_cost` is the cost basis per share/unit,
    used only for unrealized P&L, never for any recommendation."""

    symbol: str
    quantity: float
    average_cost: Optional[float] = None


@dataclass(frozen=True)
class HoldingAnalysis:
    """One holding's analysis: input (`Holding`) plus everything
    reused from `AnalystEngine.analyze()` plus the portfolio-level
    numbers only this layer can compute (market value, weight, P&L).

    `report` is `None` when the symbol could not be analyzed
    (insufficient technical *and* fundamental data, or an unexpected
    error) -- the same honest-degradation discipline
    `src.market_intelligence.types.SymbolScanOutcome` already
    establishes one layer over. All portfolio-level aggregations must
    handle `report is None` by excluding that holding, never by
    fabricating a score for it.
    """

    symbol: str
    sector: Optional[str]
    quantity: float
    average_cost: Optional[float]
    latest_price: Optional[float]
    market_value: Optional[float]
    weight: Optional[float]  # market_value / total_portfolio_value, 0..1
    unrealized_pnl: Optional[float]
    unrealized_pnl_pct: Optional[float]
    report: Optional[AnalystReport]
    error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.report is not None

    @property
    def recommendation(self):
        return self.report.decision.recommendation if self.report else None

    @property
    def confidence(self) -> Optional[float]:
        return self.report.decision.confidence if self.report else None

    @property
    def risk_level(self) -> Optional[RiskLevel]:
        return self.report.decision.risk_level if self.report else None

    @property
    def position_size(self) -> Optional[PositionSize]:
        return self.report.decision.position_size if self.report else None


@dataclass(frozen=True)
class AllocationEntry:
    symbol: str
    sector: Optional[str]
    quantity: float
    market_value: Optional[float]
    weight: Optional[float]


@dataclass(frozen=True)
class AllocationBreakdown:
    entries: List[AllocationEntry]
    cash: float
    cash_weight: float
    total_value: float
    generated_at: datetime


@dataclass(frozen=True)
class SectorExposure:
    sector: str
    market_value: float
    weight: float  # dollar-weighted share of total portfolio value, 0..1
    holdings_count: int
    symbols: List[str]


@dataclass(frozen=True)
class ConcentrationRisk:
    """Herfindahl-Hirschman-Index-based concentration measure.
    `herfindahl_index` runs 0 (perfectly diversified, infinite
    holdings) to 1 (a single position) over *position* weights;
    `sector_herfindahl_index` is the same formula over *sector*
    weights."""

    herfindahl_index: float
    sector_herfindahl_index: float
    largest_position_symbol: Optional[str]
    largest_position_weight: Optional[float]
    top_3_weight: float
    is_concentrated: bool
    concentration_threshold: float


@dataclass(frozen=True)
class DiversificationScore:
    score: float  # 0-100, 100 = maximally diversified
    effective_number_of_holdings: float  # 1 / herfindahl_index
    effective_number_of_sectors: float
    sector_count: int
    holdings_count: int
    narrative: str


@dataclass(frozen=True)
class CorrelationMatrix:
    symbols: List[str]
    matrix: Dict[str, Dict[str, float]]
    lookback_days: int
    excluded_symbols: List[str]  # insufficient overlapping price history


@dataclass(frozen=True)
class PortfolioRiskProfile:
    risk_score: float  # 0-100, 100 = highest risk
    risk_level: RiskLevel
    expected_volatility_annualized_pct: Optional[float]
    estimated_max_drawdown_pct: Optional[float]
    portfolio_beta: Optional[float]
    beta_unavailable_reason: Optional[str]
    correlation_matrix: Optional[CorrelationMatrix]
    excluded_from_volatility: List[str]
    narrative: str


@dataclass(frozen=True)
class CashRecommendation:
    current_cash: float
    current_cash_pct: float
    recommended_cash_pct_min: float
    recommended_cash_pct_max: float
    recommended_cash_amount_min: float
    recommended_cash_amount_max: float
    is_within_target_band: bool
    rationale: str


@dataclass(frozen=True)
class RebalanceAction:
    symbol: str
    action: PositionAction
    current_weight: Optional[float]
    rationale: str
    recommendation: Optional[str] = None
    confidence: Optional[float] = None


@dataclass(frozen=True)
class NewBuyOpportunity:
    symbol: str
    sector: Optional[str]
    recommendation: str
    confidence: Optional[float]
    final_score: Optional[float]
    rationale: str


@dataclass(frozen=True)
class RebalancePlan:
    actions: List[RebalanceAction]
    new_buy_opportunities: List[NewBuyOpportunity]
    generated_at: datetime
    new_buy_opportunities_source: str  # discloses where opportunities came from (or why there are none)


@dataclass(frozen=True)
class PortfolioHealthScore:
    score: float  # 0-100
    band: HealthBand
    components: Dict[str, float]
    narrative: str


@dataclass(frozen=True)
class OptimizationRecommendation:
    priority: int  # 1 = highest priority
    title: str
    rationale: str


@dataclass(frozen=True)
class PortfolioRecommendations:
    rebalance_actions: List[RebalanceAction]
    new_buy_opportunities: List[NewBuyOpportunity]
    cash_recommendation: CashRecommendation
    optimization_recommendations: List[OptimizationRecommendation]
    generated_at: datetime


@dataclass(frozen=True)
class PortfolioAnalysis:
    """The Portfolio Intelligence Layer's full output for one
    portfolio -- every field below is reused or derived from data
    already computed elsewhere in this codebase; nothing here is
    fabricated."""

    portfolio_id: int
    name: str
    holdings: List[HoldingAnalysis]
    cash: float
    total_value: float
    allocation: AllocationBreakdown
    sector_exposure: List[SectorExposure]
    concentration: ConcentrationRisk
    diversification: DiversificationScore
    risk_profile: PortfolioRiskProfile
    recommendations: PortfolioRecommendations
    health_score: PortfolioHealthScore
    generated_at: datetime
    extra: Dict[str, Any] = field(default_factory=dict)
