"""ReflectionReport: one day's automated review of that day's evaluated
`RecommendationOutcome` rows -- E6 (part 2 of 2) of the AI Evolution
Layer. `key_findings`/`improvement_suggestions` are plain descriptive
statistics and templated observations, not LLM-generated prose (this
milestone doesn't call an LLM at all) -- suggestions only, never
applied to production automatically. One row per `review_date`
(idempotent: re-running for an already-reflected-on day updates that
day's row rather than duplicating it).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, Integer, Numeric
from sqlalchemy.sql import func

from src.core.db.database import Base


class ReflectionReport(Base):
    __tablename__ = "reflection_reports"

    id = Column(Integer, primary_key=True)
    review_date = Column(Date, nullable=False, unique=True, index=True)

    recommendations_reviewed = Column(Integer, nullable=False)
    successful_count = Column(Integer, nullable=False)
    failed_count = Column(Integer, nullable=False)
    partial_count = Column(Integer, nullable=False)
    expired_count = Column(Integer, nullable=False)
    win_rate = Column(Numeric(6, 4), nullable=True)

    key_findings = Column(JSON, nullable=False)
    improvement_suggestions = Column(JSON, nullable=False)

    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ReflectionReport review_date={self.review_date!r} recommendations_reviewed={self.recommendations_reviewed!r}>"
