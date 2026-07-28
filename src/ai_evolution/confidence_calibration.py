"""E3 of the AI Evolution Layer: fits a function that maps a
recommendation's raw 0-100 confidence score onto its actual,
empirically-observed success probability, using real outcome history
(`RecommendationOutcome`) -- and governs that fit through the exact
same propose -> test -> activate -> rollback lifecycle
`src.backtesting.calibration.engine.CalibrationEngine` already
established for contributor-WEIGHT calibration, a deliberately
different concept from this one (see
`src.domain.models.confidence_calibration_model`'s module docstring).

Method selection (a stated, reasoned design decision, not the literal
three-method request): Platt scaling (logistic regression of the
binary outcome on raw confidence) is the primary method, chosen for
its low overfitting risk on the small early sample sizes this system
will actually see; isotonic regression is used automatically once the
training sample exceeds `ISOTONIC_SAMPLE_SIZE_THRESHOLD` (1000),
where a more flexible, non-parametric fit becomes trustworthy.
Temperature scaling is not implemented -- it is designed for
multi-class classifier logits, not a single scalar confidence score
paired with a binary outcome, and does not fit this data shape.

Never wired into live recommendation output by this milestone --
`activate()` only changes which row has `status=ACTIVE`; applying an
active calibration to a real `/decision` response is deliberately out
of scope here, the same disclosed boundary
`CalibrationEngine.activate()` already draws for contributor weights.
"""

import math
import uuid
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

from src.domain.models import (
    ConfidenceCalibrationMethod,
    ConfidenceCalibrationModel,
    ConfidenceCalibrationStatus,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
)

# Below this many labeled (confidence, success/failure) pairs, a fitted
# calibration curve is noise, not signal -- the same floor
# statistical_calibration.py's DEFAULT_MIN_SAMPLE_SIZE uses for exactly
# this reason.
DEFAULT_MIN_SAMPLE_SIZE = 30
ISOTONIC_SAMPLE_SIZE_THRESHOLD = 1000

# Which of a snapshot's several RecommendationOutcome rows (one per
# horizon) counts as "the" ground truth for a confidence-calibration
# training pass. 7 days is short enough to accumulate a usable sample
# quickly and long enough to be a meaningful judgment of the call --
# a configurable choice (see `propose()`'s `reference_horizon_days`
# parameter), not a hidden assumption.
DEFAULT_REFERENCE_HORIZON_DAYS = 7

_CONFIDENCE_BUCKET_EDGES = [0, 20, 40, 60, 80, 100]

# Outcome statuses treated as an unambiguous binary label. PARTIAL
# (both thresholds touched, or neither) and EXPIRED (nothing to judge
# against) are excluded -- training a calibration curve on an
# ambiguous label would launder that ambiguity into false precision.
_SUCCESS_STATUS = RecommendationOutcomeStatus.SUCCESSFUL
_FAILURE_STATUS = RecommendationOutcomeStatus.FAILED


def _generate_version() -> str:
    return f"conf-cal-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _expected_calibration_error(pairs: List[Tuple[float, int]]) -> Optional[float]:
    """The same bucket-count-weighted mean-absolute-gap ECE formula
    `src.backtesting.metrics.calibration_error()` already uses,
    reimplemented here to operate directly on (confidence_0_100,
    binary_label) pairs -- `RecommendationOutcome.status` already *is*
    the binary label, so building it through
    `EvaluationOutcome`/`_directional_pnl_pct` (which derive a label
    from recommendation direction + forward return) would be an
    unnecessary detour, not a reuse."""
    if not pairs:
        return None
    total = 0
    weighted_error = 0.0
    for low, high in zip(_CONFIDENCE_BUCKET_EDGES[:-1], _CONFIDENCE_BUCKET_EDGES[1:]):
        in_bucket = [
            label for confidence, label in pairs if low <= confidence < high or (high == 100 and confidence == 100)
        ]
        if not in_bucket:
            continue
        mean_confidence = sum(
            confidence for confidence, _ in pairs if low <= confidence < high or (high == 100 and confidence == 100)
        ) / len(in_bucket)
        realized_accuracy = sum(in_bucket) / len(in_bucket)
        weighted_error += len(in_bucket) * abs(mean_confidence / 100.0 - realized_accuracy)
        total += len(in_bucket)
    if total == 0:
        return None
    return weighted_error / total


def _load_training_pairs(
    session: Session,
    training_period_start: date,
    training_period_end: date,
    reference_horizon_days: int = DEFAULT_REFERENCE_HORIZON_DAYS,
) -> List[Tuple[float, int]]:
    rows = (
        session.query(RecommendationSnapshot.confidence_score, RecommendationOutcome.status)
        .join(RecommendationOutcome, RecommendationOutcome.snapshot_id == RecommendationSnapshot.id)
        .filter(
            RecommendationOutcome.evaluation_horizon_days == reference_horizon_days,
            RecommendationOutcome.status.in_([_SUCCESS_STATUS, _FAILURE_STATUS]),
            RecommendationSnapshot.evaluated_at >= training_period_start,
            RecommendationSnapshot.evaluated_at <= training_period_end,
        )
        .all()
    )
    return [(float(confidence), 1 if status is _SUCCESS_STATUS else 0) for confidence, status in rows]


def _fit_platt(pairs: List[Tuple[float, int]]) -> Dict[str, float]:
    labels = {label for _, label in pairs}
    if len(labels) < 2:
        raise ValueError(
            "Cannot fit a Platt-scaling model: every training example has the same outcome label "
            "(all successes or all failures) -- there is no separation for logistic regression to learn."
        )
    x = [[confidence / 100.0] for confidence, _ in pairs]
    y = [label for _, label in pairs]
    model = LogisticRegression()
    model.fit(x, y)
    return {"coef": float(model.coef_[0][0]), "intercept": float(model.intercept_[0])}


def _fit_isotonic(pairs: List[Tuple[float, int]]) -> Dict[str, List[float]]:
    x = [confidence / 100.0 for confidence, _ in pairs]
    y = [float(label) for _, label in pairs]
    model = IsotonicRegression(out_of_bounds="clip")
    model.fit(x, y)
    return {"x_thresholds": model.X_thresholds_.tolist(), "y_thresholds": model.y_thresholds_.tolist()}


def apply_calibration(model_row: ConfidenceCalibrationModel, raw_confidence: float) -> float:
    """Maps a raw 0-100 confidence score onto its calibrated 0-1
    success probability using `model_row`'s fitted parameters. Never
    called automatically by any route in this milestone -- see module
    docstring."""
    x = raw_confidence / 100.0
    params = model_row.model_params
    if model_row.method is ConfidenceCalibrationMethod.PLATT:
        z = params["coef"] * x + params["intercept"]
        return 1.0 / (1.0 + math.exp(-z))

    x_thresholds = params["x_thresholds"]
    y_thresholds = params["y_thresholds"]
    if x <= x_thresholds[0]:
        return y_thresholds[0]
    if x >= x_thresholds[-1]:
        return y_thresholds[-1]
    for i in range(len(x_thresholds) - 1):
        x0, x1 = x_thresholds[i], x_thresholds[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y_thresholds[i]
            fraction = (x - x0) / (x1 - x0)
            y0, y1 = y_thresholds[i], y_thresholds[i + 1]
            return y0 + fraction * (y1 - y0)
    return y_thresholds[-1]  # pragma: no cover -- unreachable given the bounds checks above


class ConfidenceCalibrationEngine:
    def get_active_model(self, session: Session) -> Optional[ConfidenceCalibrationModel]:
        return (
            session.query(ConfidenceCalibrationModel)
            .filter_by(status=ConfidenceCalibrationStatus.ACTIVE)
            .one_or_none()
        )

    def propose(
        self,
        session: Session,
        training_period_start: date,
        training_period_end: date,
        reference_horizon_days: int = DEFAULT_REFERENCE_HORIZON_DAYS,
        min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
        isotonic_threshold: int = ISOTONIC_SAMPLE_SIZE_THRESHOLD,
        notes: Optional[str] = None,
    ) -> ConfidenceCalibrationModel:
        pairs = _load_training_pairs(session, training_period_start, training_period_end, reference_horizon_days)
        n = len(pairs)
        if n < min_sample_size:
            raise ValueError(
                f"Insufficient outcome history to propose a confidence calibration model "
                f"({n} labeled outcomes, need at least {min_sample_size})."
            )

        method = ConfidenceCalibrationMethod.ISOTONIC if n > isotonic_threshold else ConfidenceCalibrationMethod.PLATT
        model_params = _fit_isotonic(pairs) if method is ConfidenceCalibrationMethod.ISOTONIC else _fit_platt(pairs)

        calibration_error_before = _expected_calibration_error(pairs)

        row = ConfidenceCalibrationModel(
            version=_generate_version(),
            status=ConfidenceCalibrationStatus.DRAFT,
            method=method,
            model_params=model_params,
            training_period_start=training_period_start,
            training_period_end=training_period_end,
            training_sample_size=n,
            calibration_error_before=calibration_error_before,
            notes=notes,
        )
        session.add(row)
        session.flush()

        calibrated_pairs = [(apply_calibration(row, confidence) * 100.0, label) for confidence, label in pairs]
        row.calibration_error_after = _expected_calibration_error(calibrated_pairs)

        session.commit()
        return row

    def test(self, session: Session, version: str) -> ConfidenceCalibrationModel:
        row = session.query(ConfidenceCalibrationModel).filter_by(version=version).one()
        if row.status != ConfidenceCalibrationStatus.DRAFT:
            raise ValueError(f"Confidence calibration {version!r} must be DRAFT to test (currently {row.status}).")

        before = row.calibration_error_before
        after = row.calibration_error_after
        if before is None or after is None:
            passed = False
            reason = "Calibration error could not be computed for the before and/or after fit -- cannot compare."
        elif after < before:
            passed = True
            reason = f"Calibration error improved from {float(before):.4f} to {float(after):.4f}."
        else:
            passed = False
            reason = f"Calibration error did not improve ({float(before):.4f} before vs {float(after):.4f} after)."

        row.status = ConfidenceCalibrationStatus.VALIDATED if passed else ConfidenceCalibrationStatus.REJECTED
        row.notes = f"{row.notes}\n{reason}" if row.notes else reason
        session.commit()
        return row

    def activate(self, session: Session, version: str) -> ConfidenceCalibrationModel:
        row = session.query(ConfidenceCalibrationModel).filter_by(version=version).one()
        if row.status != ConfidenceCalibrationStatus.VALIDATED:
            raise ValueError(f"Confidence calibration {version!r} must be VALIDATED to activate (currently {row.status}).")

        current_active = self.get_active_model(session)
        if current_active is not None:
            current_active.status = ConfidenceCalibrationStatus.SUPERSEDED
            current_active.deactivated_at = datetime.now(timezone.utc)

        row.status = ConfidenceCalibrationStatus.ACTIVE
        row.activated_at = datetime.now(timezone.utc)
        session.commit()
        return row

    def rollback(self, session: Session, to_version: Optional[str] = None) -> Optional[ConfidenceCalibrationModel]:
        current_active = self.get_active_model(session)
        if current_active is not None:
            current_active.status = ConfidenceCalibrationStatus.ROLLED_BACK
            current_active.deactivated_at = datetime.now(timezone.utc)

        if to_version is None:
            session.commit()
            return None

        target = session.query(ConfidenceCalibrationModel).filter_by(version=to_version).one()
        if target.status not in (
            ConfidenceCalibrationStatus.SUPERSEDED,
            ConfidenceCalibrationStatus.ROLLED_BACK,
            ConfidenceCalibrationStatus.VALIDATED,
        ):
            raise ValueError(f"Cannot roll back to {to_version!r} (status {target.status}).")

        target.status = ConfidenceCalibrationStatus.ACTIVE
        target.activated_at = datetime.now(timezone.utc)
        session.commit()
        return target
