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
