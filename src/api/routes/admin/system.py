"""GET /api/v1/admin/system/health -- Admin Dashboard "view system
health": real DB (`SELECT 1`) and Redis (`PING`) probes. Deliberately
self-contained (doesn't reach into main.py's module-level `kernel`
global) so it's testable in isolation and has no dependency on the
runtime kernel/worker subsystem, which is orthogonal to "can this
process reach its datastores."
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.schemas.admin import SystemHealthOut
from src.auth.rbac import require_staff_role
from src.auth.token_store import get_redis_client
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/system", tags=["admin"])


@router.get("/health", response_model=SystemHealthOut)
def get_system_health(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> SystemHealthOut:
    details = {}

    try:
        session.execute(text("SELECT 1"))
        details["database"] = "healthy"
    except Exception as exc:
        logger.error("Admin health check: database probe failed: %s", exc)
        details["database"] = "unhealthy"

    try:
        get_redis_client().ping()
        details["redis"] = "healthy"
    except Exception as exc:
        logger.error("Admin health check: redis probe failed: %s", exc)
        details["redis"] = "unhealthy"

    status = "healthy" if all(v == "healthy" for v in details.values()) else "degraded"
    return SystemHealthOut(status=status, details=details)
