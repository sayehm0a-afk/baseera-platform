"""Response schemas for the /api/v1/stocks/* routes.

Every schema that carries provider-sourced data (quote, fundamentals)
keeps `source`/`is_synthetic` -- the same honesty discipline
DevMarketDataProvider/SahmkMarketDataProvider already enforce -- so a
frontend can never mistake synthetic development data for a real
quote; it is labeled at every layer, all the way to the HTTP response.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name_en: str
    name_ar: Optional[str] = None
    sector: Optional[str] = None
    currency: str
    is_active: bool


class StockSearchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name_en: str
    name_ar: Optional[str] = None
    sector: Optional[str] = None


class StockSearchOut(BaseModel):
    query: str
    results: List[StockSearchResultOut]


class QuoteOut(BaseModel):
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    source: str
    is_synthetic: bool


class HistoricalBarOut(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class HistoryOut(BaseModel):
    symbol: str
    timeframe: str
    bars: List[HistoricalBarOut]


class TechnicalAnalysisOut(BaseModel):
    symbol: str
    timeframe: str
    bars_used: int
    as_of: datetime
    indicators: Dict[str, Any]


class FundamentalAnalysisOut(BaseModel):
    symbol: str
    period_type: str
    fiscal_period_end: Optional[str] = None
    ratios: Dict[str, Any]
    source: str
    is_synthetic: bool


class SignalOut(BaseModel):
    name: str
    description: str
    direction: str
    source: str
    impact: float


class ScoreContributionOut(BaseModel):
    source: str
    score: Optional[float] = None
    weight: float
    confidence: float
    notes: Optional[str] = None


class RecommendationOut(BaseModel):
    symbol: str
    recommendation: str
    confidence: float
    explanation: str
    technical_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    final_score: float
    contributions: List[ScoreContributionOut]
    signals: List[SignalOut]
    generated_at: datetime


class DecisionFactorBreakdownOut(BaseModel):
    category: str
    points: float
    weight: float
    confidence: float
    available: bool
    notes: Optional[str] = None


class InvestmentDecisionOut(BaseModel):
    symbol: str
    recommendation: str
    confidence: float
    final_score: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str
    expected_return_pct: Optional[float] = None
    risk_level: str
    position_size: str
    reasons: List[str]
    breakdown: List[DecisionFactorBreakdownOut]
    signals: List[SignalOut]
    generated_at: datetime

    # Phase 11: price-structure-driven fields (Fibonacci, support/
    # resistance, VWAP, Volume Profile) -- see AIDecisionEngine.decide().
    entry_quality: str = "FAIR"
    entry_quality_notes: List[str] = []
    risk_reward_ratio: Optional[float] = None
    stop_loss_basis: str = "atr"
    target_price_basis: str = "atr"
    confidence_calibration_notes: List[str] = []


class AnalystReportOut(BaseModel):
    """The Autonomous AI Analyst Framework's report for one symbol --
    everything /decision already produces (the same InvestmentDecision
    fields, unchanged) plus the twelve-section human-quality
    explanation ReasoningPipeline generates on top of it. See
    src/analysis/analyst/ for the orchestration logic; this schema
    adds no new numbers of its own."""

    symbol: str
    recommendation: str
    confidence: float
    final_score: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str
    expected_return_pct: Optional[float] = None
    risk_level: str
    position_size: str

    investment_summary: str
    technical_reasoning: str
    fundamental_reasoning: str
    risk_explanation: str
    bullish_factors: List[str]
    bearish_factors: List[str]
    confidence_explanation: str
    target_price_explanation: str
    stop_loss_explanation: str
    time_horizon_explanation: str
    alternative_scenarios: List[str]
    final_recommendation_rationale: str

    generated_at: datetime
    engine_version: str

    # Phase 11: price-structure-driven fields, same as InvestmentDecisionOut.
    entry_quality: str = "FAIR"
    entry_quality_notes: List[str] = []
    risk_reward_ratio: Optional[float] = None
    stop_loss_basis: str = "atr"
    target_price_basis: str = "atr"
    confidence_calibration_notes: List[str] = []
