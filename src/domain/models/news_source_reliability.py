"""NewsSourceReliability: a durable, per-source trust score -- every
source the News Intelligence Engine has ever ingested from gets a row.
Unknown sources get a conservative default (see
src.news_intelligence.config) on first sight; `articles_seen` is a
running count used to make the score more confident over time, never
to inflate it just because a source is prolific."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class NewsSourceReliability(Base):
    __tablename__ = "news_source_reliability"

    id = Column(Integer, primary_key=True)
    source_name = Column(String(64), nullable=False, unique=True, index=True)
    reliability_score = Column(Float, nullable=False, default=0.5, server_default="0.5")
    articles_seen = Column(Integer, nullable=False, default=0, server_default="0")
    notes = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<NewsSourceReliability source_name={self.source_name!r} reliability_score={self.reliability_score}>"
