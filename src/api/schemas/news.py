"""Response/request schemas for /api/v1/news/* and the portfolio
news-alerts route -- follows the same conventions as
src/api/schemas/backtesting.py (plain BaseModel, Field bounds for
request payloads)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NewsEntityOut(BaseModel):
    entity_type: str
    symbol: Optional[str] = None
    sector: Optional[str] = None
    label: Optional[str] = None


class NewsEventOut(BaseModel):
    id: int
    headline: str
    source: str
    source_reliability_score: Optional[float] = None
    published_at: Optional[datetime] = None
    is_synthetic: bool
    category: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    confidence: Optional[float] = None
    explanation: Optional[str] = None
    short_term_impact: Optional[float] = None
    medium_term_impact: Optional[float] = None
    long_term_impact: Optional[float] = None
    price_impact_score: Optional[float] = None
    risk_impact_score: Optional[float] = None
    volatility_impact_score: Optional[float] = None
    duplicate_count: int
    analyzed_at: Optional[datetime] = None
    analysis_model: Optional[str] = None
    entities: List[NewsEntityOut] = Field(default_factory=list)


class NewsFeedOut(BaseModel):
    symbol: Optional[str] = None
    total: int
    events: List[NewsEventOut]


class NewsRefreshRequest(BaseModel):
    limit: Optional[int] = Field(default=None, ge=1, le=100)


class NewsRefreshOut(BaseModel):
    collected: int
    already_ingested: int
    duplicates: int
    newly_analyzed: int
    analysis_unavailable: int
    analyzer_available: bool


class SourceReliabilityOut(BaseModel):
    source_name: str
    reliability_score: float
    articles_seen: int
    notes: Optional[str] = None
    updated_at: datetime


class SourceReliabilityListOut(BaseModel):
    sources: List[SourceReliabilityOut]


class PortfolioNewsAlertOut(BaseModel):
    id: int
    portfolio_id: int
    symbol: str
    news_event_id: int
    alert_type: str
    severity: str
    message: str
    message_ar: Optional[str] = None
    generated_at: datetime
    acknowledged_at: Optional[datetime] = None


class PortfolioNewsAlertListOut(BaseModel):
    alerts: List[PortfolioNewsAlertOut]
