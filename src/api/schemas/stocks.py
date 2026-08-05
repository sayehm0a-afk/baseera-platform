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


class MovingAveragePointOut(BaseModel):
    timestamp: datetime
    value: float


class TechnicalAnalysisOut(BaseModel):
    symbol: str
    timeframe: str
    bars_used: int
    as_of: datetime
    indicators: Dict[str, Any]

    # Phase 2F (Smart Chart): the real per-bar moving-average series
    # (src.analysis.technical_analysis_engine's sma_20/ema_20/vwap_20 --
    # already computed as a pandas Series, previously only exposed via
    # `indicators`' single latest() value) so the chart can draw an
    # actual line overlay instead of a single point. Leading periods
    # before a moving average's window is full are real NaN values,
    # dropped here rather than fabricated as zero/None.
    moving_averages: Dict[str, List[MovingAveragePointOut]] = {}


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


class SubScoresOut(BaseModel):
    trend_score: Optional[float] = None
    momentum_score: Optional[float] = None
    volume_score: Optional[float] = None
    liquidity_score: Optional[float] = None
    volatility_score: Optional[float] = None
    risk_reward_score: Optional[float] = None
    market_context_score: Optional[float] = None
    data_quality_score: float


class GateOutcomeOut(BaseModel):
    name: str
    passed: bool
    detail: str
    blocking: bool


class DecisionV2Out(BaseModel):
    """Decision Engine V2's Arabic-labeled, gate-checked action for one
    symbol -- see src/analysis/decision_v2/ for the full engine. Every
    number here traces back to AIDecisionEngine/TechnicalAnalysisEngine;
    this schema adds no new computation of its own, only structure and
    explainability (entry zone, extended targets, eight sub-scores, and
    the 15 publication gates that decided which `decision` value the
    evidence actually supports).

    `confidence_score` measures evidence strength/agreement, not a
    probability of guaranteed profit -- see `CONFIDENCE_DISCLAIMER_AR`.
    `analysis_disclaimer_ar` (`ANALYSIS_DISCLAIMER_AR`) must accompany
    every actionable decision shown to a user.
    """

    symbol: str
    company_name_ar: Optional[str] = None
    company_name_en: str
    sector_ar: Optional[str] = None

    decision: str
    decision_label_ar: str

    confidence_score: float
    confidence_disclaimer_ar: str
    opportunity_quality_score: float
    risk_score: float
    data_quality_score: float
    data_freshness_status: str

    current_price: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None

    expected_return_target_1: Optional[float] = None
    expected_return_target_2: Optional[float] = None
    downside_to_stop: Optional[float] = None
    risk_reward_target_1: Optional[float] = None
    risk_reward_target_2: Optional[float] = None

    expected_holding_period_min_days: Optional[int] = None
    expected_holding_period_max_days: Optional[int] = None
    expected_holding_period_label_ar: str
    horizon_type: str

    market_status: str
    decision_timestamp: datetime

    invalidation_conditions: List[str]
    positive_reasons: List[str]
    negative_reasons: List[str]
    warnings: List[str]
    recommendation_basis: str
    analysis_disclaimer_ar: str

    analysis_version: str
    data_source: str
    scan_run_id: Optional[int] = None

    sub_scores: SubScoresOut
    gates: List[GateOutcomeOut]

    # --- Phase 2A canonical extensions (see DecisionResult's own
    # docstring in src/analysis/decision_v2/types.py for what each is
    # derived from) --------------------------------------------------
    is_real_data: bool = True
    quote_timestamp: Optional[datetime] = None

    technical_confidence: Optional[float] = None
    momentum_confidence: Optional[float] = None
    liquidity_confidence: Optional[float] = None
    market_context_confidence: Optional[float] = None
    data_quality_confidence: Optional[float] = None

    trade_type: Optional[str] = None
    trade_type_label_ar: str = "غير محدد"
    time_horizon_rationale_ar: str = ""

    best_entry_price: Optional[float] = None
    accumulation_zone_low: Optional[float] = None
    accumulation_zone_high: Optional[float] = None
    entry_quality: str = "FAIR"
    entry_quality_label_ar: str = ""
    entry_status: str = "NOT_SUITABLE"
    entry_status_label_ar: str = ""

    invalidation_price: Optional[float] = None
    risk_level: str = "MEDIUM"
    risk_level_label_ar: str = ""

    estimated_days_target_1: Optional[int] = None
    estimated_days_target_2: Optional[int] = None
    estimated_days_target_3: Optional[int] = None

    nearest_support: Optional[float] = None
    major_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    major_resistance: Optional[float] = None
    breakout_level: Optional[float] = None
    breakdown_level: Optional[float] = None
    support_resistance_evidence_ar: str = ""

    current_volume: Optional[float] = None
    average_volume: Optional[float] = None
    relative_volume: Optional[float] = None
    liquidity_quality_ar: str = "غير محدد"
    accumulation_score: Optional[float] = None
    accumulation_assessment_ar: str = ""
    volume_confirms_decision: Optional[bool] = None
    abnormal_volume: bool = False

    technical_evidence: Dict[str, Any] = {}
    trend_direction_ar: str = "غير محدد"
    trend_strength_label_ar: str = "غير محدد"

    decision_summary_ar: str = ""
    why_now_ar: str = ""
    why_not_stronger_ar: str = ""
    entry_confirmation_conditions_ar: List[str] = []
    watch_next_session_ar: List[str] = []

    # --- Phase 2C: Market Risk and Exit Warning Engine -------------------
    market_risk_state: str = "INSUFFICIENT_DATA"
    market_risk_label_ar: str = "البيانات غير كافية"
    market_risk_basis_ar: str = ""
    market_risk_entry_permitted: bool = True
    market_risk_is_live: bool = False
    market_breadth_buy_count: Optional[int] = None
    market_breadth_sell_count: Optional[int] = None
    market_breadth_symbols_scanned: Optional[int] = None
    market_breadth_average_confidence: Optional[float] = None


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
