"""GET /api/v1/admin/audit-log -- Admin Dashboard "view logs," scored
down to querying AuditLog (+ AIRequest, under usage.py) rather than
tailing raw log files, which live in a container's ephemeral
filesystem and don't survive a restart anyway."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.admin import audit_log as audit_log_service
from src.api.schemas.admin import AuditLogListOut, AuditLogOut
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

router = APIRouter(prefix="/api/v1/admin/audit-log", tags=["admin"])


@router.get("", response_model=AuditLogListOut)
def list_audit_log(
    limit: int = 50,
    offset: int = 0,
    actor_user_id: Optional[int] = None,
    action: Optional[str] = None,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AuditLogListOut:
    total, logs = audit_log_service.list_admin_actions(
        session, limit=limit, offset=offset, actor_user_id=actor_user_id, action=action
    )
    return AuditLogListOut(total=total, logs=[AuditLogOut.model_validate(log) for log in logs])
