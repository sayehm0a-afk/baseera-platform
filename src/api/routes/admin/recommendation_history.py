"""GET /api/v1/admin/recommendation-history -- staff-only audit view over
the same real recommendation track record the public
/api/v1/recommendations/history route serves, extended with the raw
internal fields (per-contributor score breakdown, raw signals, active
calibration version) an operator needs to audit *why* a recommendation
was made. Reuses fetch_snapshots_with_context()/overall_status() from
the public route module -- no parallel query implementation.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.routes.recommendation_history import (
    fetch_snapshots_with_context,
    outcome_out,
    overall_status,
)
from src.api.schemas.recommendation_history import (
    RecommendationHistoryAuditItemOut,
    RecommendationHistoryAuditListOut,
)
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import RecommendationOutcome, RecommendationSnapshot, StaffRole, Stock, User

router = APIRouter(prefix="/api/v1/admin/recommendation-history", tags=["admin"])


def audit_item_out(
    snapshot: RecommendationSnapshot, stock: Optional[Stock], outcomes: List[RecommendationOutcome]
) -> RecommendationHistoryAuditItemOut:
    return RecommendationHistoryAuditItemOut(
        id=snapshot.id,
        symbol=snapshot.symbol,
        company_name_ar=stock.name_ar if stock else None,
        sector=stock.sector if stock else None,
        evaluated_at=snapshot.evaluated_at,
        recommendation=snapshot.recommendation.value,
        confidence_score=float(snapshot.confidence_score),
        calibrated_confidence_score=(
            float(snapshot.calibrated_confidence_score) if snapshot.calibrated_confidence_score is not None else None
        ),
        market_price_at_evaluation=(
            float(snapshot.market_price_at_evaluation) if snapshot.market_price_at_evaluation is not None else None
        ),
        target_price=float(snapshot.target_price) if snapshot.target_price is not None else None,
        target_price_2=float(snapshot.target_price_2) if snapshot.target_price_2 is not None else None,
        target_price_3=float(snapshot.target_price_3) if snapshot.target_price_3 is not None else None,
        stop_loss=float(snapshot.stop_loss) if snapshot.stop_loss is not None else None,
        expected_return_pct=float(snapshot.expected_return_pct) if snapshot.expected_return_pct is not None else None,
        time_horizon=snapshot.time_horizon,
        risk_level=snapshot.risk_level,
        position_size=snapshot.position_size,
        expires_at=snapshot.expires_at,
        reasons=list(snapshot.reasons or []),
        engine_version=snapshot.engine_version,
        is_paper_trade=snapshot.is_paper_trade,
        overall_status=overall_status(snapshot, outcomes),
        outcomes=[outcome_out(o) for o in outcomes],
        contributor_breakdown=list(snapshot.contributor_breakdown) if snapshot.contributor_breakdown else None,
        signals=list(snapshot.signals) if getattr(snapshot, "signals", None) else None,
        total_score=float(snapshot.total_score) if getattr(snapshot, "total_score", None) is not None else None,
        calibration_version=getattr(snapshot, "calibration_version", None),
        run_id=getattr(snapshot, "run_id", None),
        source=getattr(snapshot, "source", None),
    )


@router.get("", response_model=RecommendationHistoryAuditListOut)
def get_admin_recommendation_history(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> RecommendationHistoryAuditListOut:
    rows = fetch_snapshots_with_context(session, symbol, limit, offset)
    items = [audit_item_out(snapshot, stock, outcomes) for snapshot, stock, outcomes in rows]
    return RecommendationHistoryAuditListOut(generated_at=datetime.now(timezone.utc), total=len(items), items=items)
