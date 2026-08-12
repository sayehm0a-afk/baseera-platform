"""GET /api/v1/admin/ai-evolution/* -- the staff-only Basirah
Intelligence Dashboard (E9, Part 12 of the AI Evolution Layer design).
Every route here only reads already-persisted AI Evolution Layer
tables (`DailyIntelligenceSnapshot`/`DiscoveredPattern`/
`ReflectionReport`/`CalibrationConfig`/`ConfidenceCalibrationModel`) or
calls E8's read-only `compare_champion_vs_challenger`; none writes
anything or computes a metric that wasn't already computed by its
owning phase.

Non-negotiable per Part 14 of the design: no route here accepts a
"hide failures" parameter -- `failed_count` (dashboard, reflections) is
always present in the response, never behind an opt-in flag.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.admin.exceptions import (
    DailyIntelligenceSnapshotNotFoundError,
    ValidationSessionConflictError,
    ValidationSessionNotFoundError,
)
from src.ai_evolution.confidence_calibration import ConfidenceCalibrationEngine
from src.ai_evolution.paper_trading import (
    DEFAULT_EVALUATION_HORIZON_DAYS,
    compare_champion_vs_challenger,
    get_latest_challenger_config,
)
from src.ai_evolution.personal_performance import compute_personal_performance_dashboard
from src.ai_evolution.validation_metrics import compute_validation_session_metrics
from src.ai_evolution.validation_session_service import close_validation_session, create_validation_session
from src.api.schemas.ai_evolution import (
    CalibrationStatusOut,
    DailyIntelligenceSnapshotOut,
    DiscoveredPatternListOut,
    DiscoveredPatternOut,
    DuplicateSignalOut,
    GroupPerformanceOut,
    PaperTradeComparisonOut,
    PersonalPerformanceDashboardOut,
    RankPerformanceOut,
    ReflectionReportListOut,
    ReflectionReportOut,
    ValidationSessionCreateIn,
    ValidationSessionListOut,
    ValidationSessionMetricsOut,
    ValidationSessionOut,
)
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import (
    CalibrationConfig,
    CalibrationStatus,
    DailyIntelligenceSnapshot,
    DiscoveredPattern,
    ReflectionReport,
    StaffRole,
    User,
    ValidationSession,
)

router = APIRouter(prefix="/api/v1/admin/ai-evolution", tags=["admin"])


@router.get("/dashboard", response_model=DailyIntelligenceSnapshotOut)
def get_dashboard_snapshot(
    snapshot_date: Optional[date] = Query(None, description="Defaults to the most recently aggregated day."),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> DailyIntelligenceSnapshotOut:
    query = session.query(DailyIntelligenceSnapshot)
    row = (
        query.filter_by(snapshot_date=snapshot_date).one_or_none()
        if snapshot_date is not None
        else query.order_by(DailyIntelligenceSnapshot.snapshot_date.desc()).first()
    )
    if row is None:
        raise DailyIntelligenceSnapshotNotFoundError(
            f"No daily intelligence snapshot found for {snapshot_date.isoformat() if snapshot_date else 'any date'}."
        )
    return DailyIntelligenceSnapshotOut.model_validate(row)


@router.get("/calibration-status", response_model=CalibrationStatusOut)
def get_calibration_status(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> CalibrationStatusOut:
    active_weight = session.query(CalibrationConfig).filter_by(status=CalibrationStatus.ACTIVE).one_or_none()
    active_confidence = ConfidenceCalibrationEngine().get_active_model(session)
    challenger = get_latest_challenger_config(session)

    return CalibrationStatusOut(
        active_weight_calibration_version=active_weight.version if active_weight else None,
        active_weight_calibration_activated_at=active_weight.activated_at if active_weight else None,
        active_confidence_calibration_version=active_confidence.version if active_confidence else None,
        active_confidence_calibration_method=active_confidence.method.value if active_confidence else None,
        active_confidence_calibration_activated_at=active_confidence.activated_at if active_confidence else None,
        latest_validated_challenger_version=challenger.version if challenger else None,
    )


@router.get("/patterns", response_model=DiscoveredPatternListOut)
def list_discovered_patterns(
    still_valid: Optional[bool] = Query(None, description="Filter by still_valid; omit to return every pattern."),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> DiscoveredPatternListOut:
    query = session.query(DiscoveredPattern)
    if still_valid is not None:
        query = query.filter_by(still_valid=still_valid)
    rows = query.order_by(DiscoveredPattern.win_rate.desc()).all()
    return DiscoveredPatternListOut(patterns=[DiscoveredPatternOut.model_validate(r) for r in rows])


@router.get("/reflections", response_model=ReflectionReportListOut)
def list_reflection_reports(
    limit: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> ReflectionReportListOut:
    rows = session.query(ReflectionReport).order_by(ReflectionReport.review_date.desc()).limit(limit).all()
    return ReflectionReportListOut(reports=[ReflectionReportOut.model_validate(r) for r in rows])


@router.get("/paper-trade-comparison", response_model=PaperTradeComparisonOut)
def get_paper_trade_comparison(
    evaluation_horizon_days: int = Query(DEFAULT_EVALUATION_HORIZON_DAYS, ge=1),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> PaperTradeComparisonOut:
    result = compare_champion_vs_challenger(session, evaluation_horizon_days=evaluation_horizon_days)
    return PaperTradeComparisonOut(evaluation_horizon_days=evaluation_horizon_days, **result.__dict__)


@router.get("/personal-performance", response_model=PersonalPerformanceDashboardOut)
def get_personal_performance_dashboard(
    evaluation_horizon_days: int = Query(7, ge=1),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.OWNER)),
) -> PersonalPerformanceDashboardOut:
    """OWNER-only (CONT Phase 3): decision/entry-status/market-risk-state
    distributions from the real personal-scan product surface
    (DecisionV2Snapshot), plus target/stop hit rates, MFE/MAE, realized
    return, and confidence calibration from real tracked outcomes
    (RecommendationOutcome/RecommendationSnapshot) -- never a
    fabricated figure, never hidden behind a "successes only" filter."""
    result = compute_personal_performance_dashboard(session, evaluation_horizon_days=evaluation_horizon_days)
    return PersonalPerformanceDashboardOut(
        generated_at=result.generated_at,
        evaluation_horizon_days=result.evaluation_horizon_days,
        total_decisions_issued=result.total_decisions_issued,
        decision_distribution=result.decision_distribution,
        entry_status_distribution=result.entry_status_distribution,
        market_risk_state_distribution=result.market_risk_state_distribution,
        sector_distribution=result.sector_distribution,
        outcome_sample_size=result.outcome_sample_size,
        terminal_outcome_sample_size=result.terminal_outcome_sample_size,
        status_counts=result.status_counts,
        target_1_hit_rate=result.target_1_hit_rate,
        target_2_hit_rate=result.target_2_hit_rate,
        target_3_hit_rate=result.target_3_hit_rate,
        stop_loss_hit_rate=result.stop_loss_hit_rate,
        expired_count=result.expired_count,
        unresolved_count=result.unresolved_count,
        average_max_favorable_excursion_pct=result.average_max_favorable_excursion_pct,
        average_max_adverse_excursion_pct=result.average_max_adverse_excursion_pct,
        average_realized_return_pct=result.average_realized_return_pct,
        average_time_to_target_days=result.average_time_to_target_days,
        calibration_by_bucket=result.calibration_by_bucket,
        calibration_by_type=result.calibration_by_type,
        calibration_by_holding_period=result.calibration_by_holding_period,
        calibration_by_sector=result.calibration_by_sector,
        market_risk_state_calibration_unavailable_ar=result.market_risk_state_calibration_unavailable_ar,
        strongest_groups=[GroupPerformanceOut(**g.__dict__) for g in result.strongest_groups],
        weakest_groups=[GroupPerformanceOut(**g.__dict__) for g in result.weakest_groups],
        small_sample_warning=result.small_sample_warning,
        insufficient_data_message_ar=result.insufficient_data_message_ar,
    )


# ======================================================================
# M10: validation-session lifecycle (start/close/list) + per-session
# metrics. OWNER-only for anything that opens or closes a session --
# the mutating action that decides what evidence a live M10 measurement
# is even allowed to claim -- while listing/metrics stay at ADMIN,
# matching the read-only routes above.
# ======================================================================


@router.post("/validation-sessions", response_model=ValidationSessionOut, status_code=201)
def create_validation_session_route(
    payload: ValidationSessionCreateIn,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.OWNER)),
) -> ValidationSessionOut:
    try:
        record = create_validation_session(
            session,
            payload.name,
            is_dry_run=payload.is_dry_run,
            created_by_user_id=current_user.id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise ValidationSessionConflictError(str(exc)) from exc
    return ValidationSessionOut.model_validate(record)


@router.post("/validation-sessions/{validation_session_id}/close", response_model=ValidationSessionOut)
def close_validation_session_route(
    validation_session_id: int,
    aborted: bool = Query(False, description="True to mark ABORTED instead of the normal CLOSED."),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.OWNER)),
) -> ValidationSessionOut:
    try:
        record = close_validation_session(session, validation_session_id, aborted=aborted)
    except ValueError as exc:
        raise ValidationSessionConflictError(str(exc)) from exc
    return ValidationSessionOut.model_validate(record)


@router.get("/validation-sessions", response_model=ValidationSessionListOut)
def list_validation_sessions(
    is_dry_run: Optional[bool] = Query(None, description="Filter by is_dry_run; omit to return every session."),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> ValidationSessionListOut:
    query = session.query(ValidationSession)
    if is_dry_run is not None:
        query = query.filter_by(is_dry_run=is_dry_run)
    rows = query.order_by(ValidationSession.started_at.desc()).all()
    return ValidationSessionListOut(sessions=[ValidationSessionOut.model_validate(r) for r in rows])


@router.get("/validation-sessions/{validation_session_id}", response_model=ValidationSessionOut)
def get_validation_session(
    validation_session_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> ValidationSessionOut:
    record = session.query(ValidationSession).filter_by(id=validation_session_id).one_or_none()
    if record is None:
        raise ValidationSessionNotFoundError(f"Validation session {validation_session_id} not found.")
    return ValidationSessionOut.model_validate(record)


@router.get("/validation-sessions/{validation_session_id}/metrics", response_model=ValidationSessionMetricsOut)
def get_validation_session_metrics(
    validation_session_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> ValidationSessionMetricsOut:
    record = session.query(ValidationSession).filter_by(id=validation_session_id).one_or_none()
    if record is None:
        raise ValidationSessionNotFoundError(f"Validation session {validation_session_id} not found.")
    result = compute_validation_session_metrics(session, validation_session_id)
    return ValidationSessionMetricsOut(
        validation_session_id=result.validation_session_id,
        total_signals_issued=result.total_signals_issued,
        actionable_signals=result.actionable_signals,
        status_counts=result.status_counts,
        win_rate=result.win_rate,
        decisive_signal_count=result.decisive_signal_count,
        false_positive_rate=result.false_positive_rate,
        target_hit_rate_by_target=result.target_hit_rate_by_target,
        stop_loss_rate=result.stop_loss_rate,
        average_return_pct=result.average_return_pct,
        expectancy_pct=result.expectancy_pct,
        average_time_to_target_days=result.average_time_to_target_days,
        average_time_to_stop_days=result.average_time_to_stop_days,
        ranking_position_performance=[
            RankPerformanceOut(**r.__dict__) for r in result.ranking_position_performance
        ],
        calibration_pair_count=result.calibration_pair_count,
        expected_calibration_error=result.expected_calibration_error,
        duplicate_signals=[DuplicateSignalOut(**d.__dict__) for d in result.duplicate_signals],
        duplicate_signal_rate=result.duplicate_signal_rate,
        data_unavailable_count=result.data_unavailable_count,
        data_unavailable_rate=result.data_unavailable_rate,
        pending_count=result.pending_count,
        cancelled_count=result.cancelled_count,
        partial_count=result.partial_count,
    )
