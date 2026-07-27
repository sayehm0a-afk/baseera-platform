"""POST/GET /api/v1/calibrations/* -- REST layer over
src.backtesting.calibration.engine.CalibrationEngine, following the
same conventions as src/api/routes/backtests.py.

Every route is staff-only (Phase 10 plan decision 10: tuning/activating
a calibration is an ops action, not a customer feature -- unlike
backtests, which back the customer-facing "Strategies" screen).
SUPPORT is the minimum role since this is routine ops work, not an
account-management action.

`/validate` runs synchronously within the request (unlike
`POST /api/v1/backtests`) -- it is bounded by the same symbol-count/
date-range limits as a backtest (CalibrationValidateRequest reuses
those validators), so it is never a "large full-market backtest" by
construction. A genuinely asynchronous validate-in-background is a
disclosed, natural extension not built in this milestone (see
docs/BACKTESTING_AND_CALIBRATION.md).
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.exceptions import CalibrationNotFoundError, InvalidCalibrationTransitionError
from src.api.schemas.backtesting import (
    CalibrationConfigOut,
    CalibrationCreateRequest,
    CalibrationListOut,
    CalibrationValidateRequest,
    IndicatorAttributionOut,
    IndicatorAttributionRequest,
    StatisticalCalibrationEntryOut,
    StatisticalCalibrationOut,
    StatisticalCalibrationRequest,
)
from src.auth.rbac import require_staff_role
from src.backtesting.calibration.engine import CalibrationEngine
from src.backtesting.calibration.indicator_attribution import run_indicator_attribution
from src.backtesting.calibration.statistical_calibration import propose_statistical_weights
from src.core.db.database import get_db
from src.domain.models import CalibrationConfig, DataProvenanceMode, StaffRole, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calibrations", tags=["calibrations"])


def _to_calibration_out(row: CalibrationConfig) -> CalibrationConfigOut:
    return CalibrationConfigOut(
        version=row.version,
        status=row.status.value,
        config=row.config,
        training_period_start=row.training_period_start,
        training_period_end=row.training_period_end,
        validation_period_start=row.validation_period_start,
        validation_period_end=row.validation_period_end,
        metrics=row.metrics,
        baseline_comparison_metrics=row.baseline_comparison_metrics,
        random_seed=row.random_seed,
        notes=row.notes,
        created_at=row.created_at,
        activated_at=row.activated_at,
        deactivated_at=row.deactivated_at,
    )


def _get_calibration_or_404(session: Session, version: str) -> CalibrationConfig:
    row = session.query(CalibrationConfig).filter_by(version=version).one_or_none()
    if row is None:
        raise CalibrationNotFoundError(f"No calibration configuration {version!r}.")
    return row


@router.post("", response_model=CalibrationConfigOut)
def create_calibration(
    request: CalibrationCreateRequest,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT)),
) -> CalibrationConfigOut:
    row = CalibrationEngine().propose(
        session,
        config=request.config,
        training_period=(request.training_period_start, request.training_period_end),
        validation_period=(request.validation_period_start, request.validation_period_end),
        notes=request.notes,
        random_seed=request.random_seed,
    )
    return _to_calibration_out(row)


@router.get("", response_model=CalibrationListOut)
def list_calibrations(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT))
) -> CalibrationListOut:
    rows = session.query(CalibrationConfig).order_by(CalibrationConfig.created_at.desc()).all()
    return CalibrationListOut(calibrations=[_to_calibration_out(row) for row in rows])


@router.get("/{version}", response_model=CalibrationConfigOut)
def get_calibration(
    version: str, session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT))
) -> CalibrationConfigOut:
    return _to_calibration_out(_get_calibration_or_404(session, version))


@router.post("/{version}/validate", response_model=CalibrationConfigOut)
def validate_calibration(
    version: str,
    request: CalibrationValidateRequest,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT)),
) -> CalibrationConfigOut:
    _get_calibration_or_404(session, version)
    try:
        result = CalibrationEngine().validate(
            session,
            version,
            symbols=request.symbols,
            data_provenance_mode=DataProvenanceMode(request.data_provenance_mode),
            evaluation_frequency_days=request.evaluation_frequency_days,
            holding_horizon_days=request.holding_horizon_days,
            target_price_horizon_days=request.target_price_horizon_days,
            transaction_cost_bps=request.transaction_cost_bps,
            slippage_bps=request.slippage_bps,
            confidence_threshold=request.confidence_threshold,
            recommendation_threshold=request.recommendation_threshold,
            fundamental_reporting_lag_days=request.fundamental_reporting_lag_days,
        )
    except ValueError as exc:
        raise InvalidCalibrationTransitionError(str(exc)) from exc
    return _to_calibration_out(result)


@router.post("/{version}/activate", response_model=CalibrationConfigOut)
def activate_calibration(
    version: str, session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT))
) -> CalibrationConfigOut:
    _get_calibration_or_404(session, version)
    try:
        result = CalibrationEngine().activate(session, version)
    except ValueError as exc:
        raise InvalidCalibrationTransitionError(str(exc)) from exc
    return _to_calibration_out(result)


@router.post("/{version}/rollback", response_model=CalibrationConfigOut)
def rollback_calibration(
    version: str, session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT))
) -> CalibrationConfigOut:
    """Rolls back to `version` -- deactivates whatever is currently
    ACTIVE and reactivates this specific prior version."""
    _get_calibration_or_404(session, version)
    try:
        result = CalibrationEngine().rollback(session, to_version=version)
    except ValueError as exc:
        raise InvalidCalibrationTransitionError(str(exc)) from exc
    return _to_calibration_out(result)


@router.post("/indicator-attribution", response_model=IndicatorAttributionOut)
def run_indicator_attribution_route(
    request: IndicatorAttributionRequest,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT)),
) -> IndicatorAttributionOut:
    """Replays historical data and scores each of the eleven named
    indicators' (Fibonacci, Support/Resistance, VWAP, Volume Profile,
    RSI, MACD, ADX, EMA, SMA, Bollinger, ATR) standalone predictive
    power in isolation -- see src.backtesting.calibration.indicator_attribution.
    Runs synchronously, bounded the same way /calibrations/{version}/validate is."""
    report = run_indicator_attribution(
        session,
        symbols=request.symbols,
        start_date=request.start_date,
        end_date=request.end_date,
        data_provenance_mode=DataProvenanceMode(request.data_provenance_mode),
        evaluation_frequency_days=request.evaluation_frequency_days,
        holding_horizon_days=request.holding_horizon_days,
        fundamental_reporting_lag_days=request.fundamental_reporting_lag_days,
    )
    return IndicatorAttributionOut(
        evaluated_count=report.evaluated_count,
        skipped=report.skipped,
        directional_indicators=report.directional_indicators,
        risk_indicators=report.risk_indicators,
    )


@router.post("/statistical-weights", response_model=StatisticalCalibrationOut)
def propose_statistical_weights_route(
    request: StatisticalCalibrationRequest,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.SUPPORT)),
) -> StatisticalCalibrationOut:
    """Measures each of the eleven scoring contributors' own standalone
    directional edge over the training period, statistically tests it
    against "no real edge," and proposes a new weight only where the
    evidence supports one -- see
    src.backtesting.calibration.statistical_calibration. When
    `create_draft_calibration` is set, any reweighted contributor is
    handed straight to CalibrationEngine.propose() as a new DRAFT
    CalibrationConfig, ready for the existing validate -> activate ->
    rollback lifecycle."""
    report = propose_statistical_weights(
        session,
        symbols=request.symbols,
        training_period_start=request.training_period_start,
        training_period_end=request.training_period_end,
        data_provenance_mode=DataProvenanceMode(request.data_provenance_mode),
        evaluation_frequency_days=request.evaluation_frequency_days,
        holding_horizon_days=request.holding_horizon_days,
        fundamental_reporting_lag_days=request.fundamental_reporting_lag_days,
        min_sample_size=request.min_sample_size,
        significance_level=request.significance_level,
    )

    draft_version = None
    if request.create_draft_calibration and report.contributor_weights:
        draft = CalibrationEngine().propose(
            session,
            config={"contributor_weights": report.contributor_weights},
            training_period=(request.training_period_start, request.training_period_end),
            validation_period=(request.validation_period_start, request.validation_period_end),
            notes=request.notes or "Statistically-calibrated contributor weights (see indicator/statistical calibration report).",
        )
        draft_version = draft.version

    return StatisticalCalibrationOut(
        training_period_start=report.training_period_start,
        training_period_end=report.training_period_end,
        symbols=report.symbols,
        entries=[
            StatisticalCalibrationEntryOut(
                contributor=e.contributor, old_weight=e.old_weight, new_weight=e.new_weight,
                sample_size=e.sample_size, mean_edge=e.mean_edge, t_statistic=e.t_statistic,
                p_value=e.p_value, significant=e.significant, action=e.action,
            )
            for e in report.entries
        ],
        draft_calibration_version=draft_version,
    )
