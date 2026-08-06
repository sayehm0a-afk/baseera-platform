"""One (RecommendationSnapshot, horizon) evaluation slot -- the durable
record of whether a live recommendation's target/stop was reached by a
fixed number of days after it was made. Rows are created PENDING at
the same time a `RecommendationSnapshot` is written (one per configured
horizon -- see `src.ai_evolution.outcome_evaluation.EVALUATION_HORIZON_DAYS`)
and are only ever transitioned forward by `OutcomeEvaluationScheduler`
once real price data covering the horizon exists -- never judged before
the horizon has actually elapsed, and never deleted or overwritten
after a terminal status is reached (Part 11 of the AI Evolution Layer
design: the historical performance record is append-only).
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class RecommendationOutcomeStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class RecommendationOutcome(Base):
    """`status` starts PENDING and is set exactly once by the scheduler
    (SUCCESSFUL/FAILED/PARTIAL/EXPIRED) or, in principle, by a future
    manual administrative action (CANCELLED -- never set automatically
    by this milestone). The unique constraint makes issuance idempotent:
    re-running the issuance step for a snapshot that already has a row
    for a given horizon is a no-op, not a duplicate.
    """

    __tablename__ = "recommendation_outcomes"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "evaluation_horizon_days", name="uq_recommendation_outcome_identity"),
    )

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("recommendation_snapshots.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)

    evaluation_horizon_days = Column(Integer, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum(RecommendationOutcomeStatus), nullable=False, default=RecommendationOutcomeStatus.PENDING, index=True)

    price_at_evaluation = Column(Numeric(18, 4), nullable=True)
    return_pct = Column(Numeric(9, 4), nullable=True)
    hit_target = Column(Boolean, nullable=True)
    hit_stop = Column(Boolean, nullable=True)

    # Per-target(1/2/3) tracking -- `hit_target` above only ever
    # tracked the single legacy target_price. Each `_reached` flag is
    # set the first time the forward price path touches that target
    # within this horizon; `_reached_at` is that bar's real timestamp,
    # never a later re-evaluation time, so time-to-target is accurate.
    target_1_reached = Column(Boolean, nullable=True)
    target_1_reached_at = Column(DateTime(timezone=True), nullable=True)
    target_2_reached = Column(Boolean, nullable=True)
    target_2_reached_at = Column(DateTime(timezone=True), nullable=True)
    target_3_reached = Column(Boolean, nullable=True)
    target_3_reached_at = Column(DateTime(timezone=True), nullable=True)

    # MFE/MAE: the best/worst the position's real forward price path
    # ever looked, as a percent of entry price, across the whole
    # horizon window -- independent of whether target/stop was
    # actually touched. `time_to_target_days` is the elapsed real days
    # from publication to the first target reached (any of the three),
    # null when none was reached within this horizon.
    max_favorable_excursion_pct = Column(Numeric(9, 4), nullable=True)
    max_adverse_excursion_pct = Column(Numeric(9, 4), nullable=True)
    time_to_target_days = Column(Integer, nullable=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    snapshot = relationship("RecommendationSnapshot")

    def __repr__(self) -> str:
        return (
            f"<RecommendationOutcome snapshot_id={self.snapshot_id!r} "
            f"horizon_days={self.evaluation_horizon_days!r} status={self.status}>"
        )
