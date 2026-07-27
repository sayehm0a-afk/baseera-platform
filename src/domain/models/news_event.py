"""NewsEvent: one analyzed, deduplicated news item -- the durable,
auditable record of what the News Intelligence Engine collected and
concluded about it.

A "canonical" event (`duplicate_of_id` is null) represents one or more
raw articles (syndicated copies/updated versions of the same story)
merged together; `duplicate_count` records how many were folded in.
Analysis fields (`category`, `sentiment_score`, ...) are nullable and
`analyzed_at`/`analysis_model` stay null when no LLM analysis has run
yet (e.g. no `OPENAI_API_KEY` configured) -- a row always exists for
every collected article, honestly reflecting "collected but not yet
analyzed" rather than fabricating a placeholder classification. See
src/news_intelligence/ for the collection/dedup/analysis pipeline that
produces these rows.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class NewsCategory(str, enum.Enum):
    EARNINGS = "EARNINGS"
    DIVIDEND = "DIVIDEND"
    CONTRACT_AWARD = "CONTRACT_AWARD"
    EXPANSION = "EXPANSION"
    ACQUISITION = "ACQUISITION"
    LAWSUIT = "LAWSUIT"
    REGULATORY_CHANGE = "REGULATORY_CHANGE"
    GOVERNMENT_POLICY = "GOVERNMENT_POLICY"
    OIL = "OIL"
    INTEREST_RATES = "INTEREST_RATES"
    INFLATION = "INFLATION"
    CURRENCY = "CURRENCY"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    PRODUCTION = "PRODUCTION"
    GUIDANCE = "GUIDANCE"
    CREDIT_RATING = "CREDIT_RATING"
    EXECUTIVE_CHANGE = "EXECUTIVE_CHANGE"
    BANKRUPTCY = "BANKRUPTCY"
    TRADING_SUSPENSION = "TRADING_SUSPENSION"
    OTHER = "OTHER"


class SentimentLabel(str, enum.Enum):
    VERY_POSITIVE = "VERY_POSITIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    VERY_NEGATIVE = "VERY_NEGATIVE"


class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True)
    # Hash of (source, headline, published_at) -- the idempotency key
    # that keeps re-ingesting the same feed from ever creating a
    # duplicate row or re-spending an LLM call on an article already
    # analyzed.
    external_key = Column(String(128), nullable=False, unique=True, index=True)

    headline = Column(Text, nullable=False)
    source = Column(String(64), nullable=False, index=True)
    source_reliability_score = Column(Float, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    is_synthetic = Column(Boolean, nullable=False, default=False, server_default="false")

    category = Column(Enum(NewsCategory), nullable=True, index=True)
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(Enum(SentimentLabel), nullable=True)
    confidence = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)

    short_term_impact = Column(Float, nullable=True)
    medium_term_impact = Column(Float, nullable=True)
    long_term_impact = Column(Float, nullable=True)
    price_impact_score = Column(Float, nullable=True)
    risk_impact_score = Column(Float, nullable=True)
    volatility_impact_score = Column(Float, nullable=True)

    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    analysis_model = Column(String(64), nullable=True)

    # Self-referential merge pointer: non-null means "this article was
    # folded into the canonical event `duplicate_of_id` points at" --
    # its own analysis fields stay null (never independently analyzed,
    # never allowed to inflate the canonical event's confidence).
    duplicate_of_id = Column(Integer, ForeignKey("news_events.id"), nullable=True, index=True)
    duplicate_count = Column(Integer, nullable=False, default=0, server_default="0")

    raw_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())

    entities = relationship(
        "NewsEntity", back_populates="news_event", cascade="all, delete-orphan", foreign_keys="NewsEntity.news_event_id"
    )
    duplicate_of = relationship("NewsEvent", remote_side=[id])

    def __repr__(self) -> str:
        return f"<NewsEvent id={self.id} category={self.category} source={self.source!r}>"
