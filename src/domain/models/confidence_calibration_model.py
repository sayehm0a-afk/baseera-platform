"""ConfidenceCalibrationModel: a versioned, durable record of one
proposed (or active) confidence-calibration fit -- a function that
maps a recommendation's raw 0-100 confidence score onto its actual,
empirically-observed success probability.

This is a DIFFERENT calibration concept from `CalibrationConfig`/
`CalibrationEngine` (which tune contributor WEIGHTS via a same-period
backtest comparison). This one tunes the CONFIDENCE NUMBER ITSELF
against real outcome history (`RecommendationOutcome`), using Platt
scaling or isotonic regression. The two are easily confused because
both use the word "calibration" -- kept as separate models/tables/
engines deliberately, not merged.

Mirrors `CalibrationConfig`'s exact lifecycle
(DRAFT -> VALIDATED -> ACTIVE, with REJECTED/SUPERSEDED/ROLLED_BACK
as the other terminal/transitional states) and the same
application-enforced "at most one ACTIVE row" invariant -- see that
model's own docstring for why this isn't a DB constraint.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class ConfidenceCalibrationStatus(str, enum.Enum):
    DRAFT = "DRAFT"  # proposed, not yet tested
    VALIDATED = "VALIDATED"  # tested: materially improves calibration error
    ACTIVE = "ACTIVE"  # currently the calibration function in effect
    REJECTED = "REJECTED"  # tested: did not materially improve calibration error
    SUPERSEDED = "SUPERSEDED"  # was active, then a newer version was activated over it
    ROLLED_BACK = "ROLLED_BACK"  # was active, then explicitly rolled back


class ConfidenceCalibrationMethod(str, enum.Enum):
    PLATT = "PLATT"
    ISOTONIC = "ISOTONIC"


class ConfidenceCalibrationModel(Base):
    __tablename__ = "confidence_calibration_models"

    id = Column(Integer, primary_key=True)
    version = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(Enum(ConfidenceCalibrationStatus), nullable=False, default=ConfidenceCalibrationStatus.DRAFT)
    method = Column(Enum(ConfidenceCalibrationMethod), nullable=False)

    # Platt: {"coef": float, "intercept": float} (a fitted logistic
    # regression, applied as sigmoid(coef * confidence + intercept)).
    # Isotonic: {"x_thresholds": [...], "y_thresholds": [...]} (the
    # fitted step function's knots, sufficient to reconstruct
    # predictions via linear interpolation without re-pickling an
    # sklearn estimator into the DB).
    model_params = Column(JSON, nullable=False)

    training_period_start = Column(Date, nullable=True)
    training_period_end = Column(Date, nullable=True)
    training_sample_size = Column(Integer, nullable=False)

    calibration_error_before = Column(Numeric(9, 6), nullable=True)
    calibration_error_after = Column(Numeric(9, 6), nullable=True)

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
        return f"<ConfidenceCalibrationModel version={self.version!r} status={self.status} method={self.method}>"
