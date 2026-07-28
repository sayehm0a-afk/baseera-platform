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

from src.admin.exceptions import DailyIntelligenceSnapshotNotFoundError
from src.ai_evolution.confidence_calibration import ConfidenceCalibrationEngine
from src.ai_evolution.paper_trading import (
    DEFAULT_EVALUATION_HORIZON_DAYS,
    compare_champion_vs_challenger,
    get_latest_challenger_config,
)
from src.api.schemas.ai_evolution import (
    CalibrationStatusOut,
    DailyIntelligenceSnapshotOut,
    DiscoveredPatternListOut,
    DiscoveredPatternOut,
    PaperTradeComparisonOut,
    ReflectionReportListOut,
    ReflectionReportOut,
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
