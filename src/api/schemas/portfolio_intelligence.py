"""Request/response schemas for /api/v1/portfolio/* -- follows the
same conventions as src/api/schemas/market_intelligence.py and
backtesting.py. Field names deliberately mirror
src.portfolio_intelligence.repository.serialize_portfolio_analysis()'s
dict shape exactly, so a persisted PortfolioAnalysisSnapshot.analysis_json
blob can be validated directly into `PortfolioAnalysisOut(**blob)` for
GET reads, with no separate deserializer to keep in sync.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class HoldingRequest(BaseModel):
    symbol: str
    quantity: float = Field(..., gt=0)
    average_cost: Optional[float] = Field(default=None, ge=0)


class PortfolioAnalyzeRequest(BaseModel):
    portfolio_id: Optional[int] = Field(
        default=None, description="Omit to create a new portfolio; provide to re-analyze an existing one with updated holdings/cash."
    )
    name: str = "My Portfolio"
    holdings: List[HoldingRequest] = Field(default_factory=list)
    cash: float = Field(default=0.0, ge=0)


class PortfolioOut(BaseModel):
    id: int
    name: str
    cash_balance: float
    created_at: datetime
    updated_at: datetime


class HoldingAnalysisOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    quantity: float
    average_cost: Optional[float] = None
    latest_price: Optional[float] = None
    market_value: Optional[float] = None
    weight: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    available: bool
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    risk_level: Optional[str] = None
    position_size: Optional[str] = None
    target_price: Optional[float] = None
    error: Optional[str] = None


class AllocationEntryOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    quantity: float
    market_value: Optional[float] = None
    weight: Optional[float] = None


class AllocationOut(BaseModel):
    entries: List[AllocationEntryOut]
    cash: float
    cash_weight: float
    total_value: float


class SectorExposureOut(BaseModel):
    sector: str
    market_value: float
    weight: float
    holdings_count: int
    symbols: List[str]


class ConcentrationOut(BaseModel):
    herfindahl_index: float
    sector_herfindahl_index: float
    largest_position_symbol: Optional[str] = None
    largest_position_weight: Optional[float] = None
    top_3_weight: float
    is_concentrated: bool
    concentration_threshold: float


class DiversificationOut(BaseModel):
    score: float
    effective_number_of_holdings: float
    effective_number_of_sectors: float
    sector_count: int
    holdings_count: int
    narrative: str


class CorrelationMatrixOut(BaseModel):
    symbols: List[str]
    matrix: Dict[str, Dict[str, float]]
    lookback_days: int
    excluded_symbols: List[str]


class RiskProfileOut(BaseModel):
    risk_score: float
    risk_level: str
    expected_volatility_annualized_pct: Optional[float] = None
    estimated_max_drawdown_pct: Optional[float] = None
    portfolio_beta: Optional[float] = None
    beta_unavailable_reason: Optional[str] = None
    correlation_matrix: Optional[CorrelationMatrixOut] = None
    excluded_from_volatility: List[str]
    narrative: str


class RebalanceActionOut(BaseModel):
    symbol: str
    action: str
    current_weight: Optional[float] = None
    rationale: str
    recommendation: Optional[str] = None
    confidence: Optional[float] = None


class NewBuyOpportunityOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    recommendation: str
    confidence: Optional[float] = None
    final_score: Optional[float] = None
    rationale: str


class RebalancePlanOut(BaseModel):
    rebalance_actions: List[RebalanceActionOut]
    new_buy_opportunities: List[NewBuyOpportunityOut]


class CashRecommendationOut(BaseModel):
    current_cash: float
    current_cash_pct: float
    recommended_cash_pct_min: float
    recommended_cash_pct_max: float
    recommended_cash_amount_min: float
    recommended_cash_amount_max: float
    is_within_target_band: bool
    rationale: str


class OptimizationRecommendationOut(BaseModel):
    priority: int
    title: str
    rationale: str


class PortfolioRecommendationsOut(BaseModel):
    rebalance_actions: List[RebalanceActionOut]
    new_buy_opportunities: List[NewBuyOpportunityOut]
    cash_recommendation: CashRecommendationOut
    optimization_recommendations: List[OptimizationRecommendationOut]


class HealthScoreOut(BaseModel):
    score: float
    band: str
    components: Dict[str, float]
    narrative: str


class PortfolioAnalysisOut(BaseModel):
    portfolio_id: int
    name: str
    cash: float
    total_value: float
    generated_at: datetime
    holdings: List[HoldingAnalysisOut]
    allocation: AllocationOut
    sector_exposure: List[SectorExposureOut]
    concentration: ConcentrationOut
    diversification: DiversificationOut
    risk_profile: RiskProfileOut
    recommendations: PortfolioRecommendationsOut
    health_score: HealthScoreOut
