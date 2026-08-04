"""CalibrationConfig: a versioned, durable record of one proposed (or
active) set of AIDecisionEngine/RecommendationEngine tuning parameters
-- contributor weights, recommendation thresholds, ATR multiples, risk
thresholds, confidence-penalty parameters -- plus the validation-period
metrics that justified it (or didn't).

At most one row has status=ACTIVE at a time; enforced by
CalibrationEngine.activate() (deactivate-then-activate in one
transaction), not a DB constraint -- a partial unique index on status
is backend-specific (trivial in Postgres, awkward in the SQLite engine
this repo's tests run against), and the application-level invariant is
just as strong here since activation only ever happens through one
code path.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class CalibrationStatus(str, enum.Enum):
    DRAFT = "DRAFT"  # proposed, not yet validated
    VALIDATED = "VALIDATED"  # validation run complete, eligible for activation
    ACTIVE = "ACTIVE"  # currently governing production AIDecisionEngine behavior
    REJECTED = "REJECTED"  # validation found it unsafe/no better than the active config
    SUPERSEDED = "SUPERSEDED"  # was active, then a newer version was activated over it
    ROLLED_BACK = "ROLLED_BACK"  # was active, then explicitly rolled back via CalibrationEngine.rollback()


class CalibrationConfig(Base):
    __tablename__ = "calibration_configs"

    id = Column(Integer, primary_key=True)
    version = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(Enum(CalibrationStatus), nullable=False, default=CalibrationStatus.DRAFT)

    # The actual proposed overrides -- contributor weights, recommendation
    # thresholds, ATR multiples, risk-level thresholds, confidence-penalty
    # parameters. Deliberately a JSON bag, not one column per parameter:
    # the tunable parameter set is expected to grow as more contributors
    # are added, the same reasoning AnalysisContext.extra already uses.
    config = Column(JSON, nullable=False)

    training_period_start = Column(Date, nullable=True)
    training_period_end = Column(Date, nullable=True)
    validation_period_start = Column(Date, nullable=True)
    validation_period_end = Column(Date, nullable=True)
    training_run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=True, index=True)
    validation_run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=True, index=True)

    # This candidate's metrics on the validation period, and the
    # currently-active config's metrics on that *same* period, computed
    # side by side -- so "is this actually better" is always an honest,
    # like-for-like comparison, never a claim against a different period.
    metrics = Column(JSON, nullable=True)
    baseline_comparison_metrics = Column(JSON, nullable=True)

    random_seed = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<CalibrationConfig version={self.version!r} status={self.status}>"
