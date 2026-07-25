"""RecommendationHistory: a durable log of every AI recommendation a
user was actually shown -- distinct from RecommendationSnapshot
(src/domain/models/recommendation_snapshot.py), which is backtesting's
point-in-time-labeled record used for anti-leakage evaluation, not a
per-user viewing log. `source` records which surface produced it
(`ai_screen`, `scan`, `portfolio`) since the same symbol/recommendation
can legitimately be shown to the same user from more than one feature.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from src.core.db.database import Base


class RecommendationHistory(Base):
    __tablename__ = "recommendation_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    symbol = Column(String(20), nullable=False, index=True)
    recommendation = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)
    source = Column(String(50), nullable=False)

    viewed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<RecommendationHistory id={self.id} user_id={self.user_id} symbol={self.symbol!r}>"
