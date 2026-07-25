"""GET /api/v1/admin/usage/ai -- Admin Dashboard "view AI usage,"
aggregated from real AIRequest rows (see src/analysis/
ai_request_recorder.py). There is deliberately no generic "API usage"
(per-endpoint request-volume) endpoint here: no per-request log table
exists in this codebase to aggregate from -- that data lives only in
the Prometheus counters already exposed at GET /metrics (scrape-based,
not a queryable JSON source). Building a fake per-endpoint usage table
with no real underlying data would be exactly the kind of fabricated
admin-dashboard content ruled out from the start; /metrics is the
honest answer to "API usage" until a real request-log table exists.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.schemas.admin import AIUsageSummaryOut
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import AIRequest, AIRequestStatus, StaffRole, User

router = APIRouter(prefix="/api/v1/admin/usage", tags=["admin"])


@router.get("/ai", response_model=AIUsageSummaryOut)
def get_ai_usage_summary(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> AIUsageSummaryOut:
    total_requests = session.query(func.count(AIRequest.id)).scalar() or 0
    success_count = session.query(func.count(AIRequest.id)).filter(AIRequest.status == AIRequestStatus.SUCCESS).scalar() or 0
    failed_count = session.query(func.count(AIRequest.id)).filter(AIRequest.status == AIRequestStatus.FAILED).scalar() or 0
    timeout_count = session.query(func.count(AIRequest.id)).filter(AIRequest.status == AIRequestStatus.TIMEOUT).scalar() or 0
    total_tokens = session.query(func.coalesce(func.sum(AIRequest.total_tokens), 0)).scalar() or 0
    estimated_cost_usd = session.query(func.coalesce(func.sum(AIRequest.estimated_cost_usd), 0)).scalar() or 0

    by_feature_rows = session.query(AIRequest.feature, func.count(AIRequest.id)).group_by(AIRequest.feature).all()

    return AIUsageSummaryOut(
        total_requests=total_requests,
        success_count=success_count,
        failed_count=failed_count,
        timeout_count=timeout_count,
        total_tokens=int(total_tokens),
        estimated_cost_usd=float(estimated_cost_usd),
        by_feature={feature: count for feature, count in by_feature_rows},
    )
