"""GET/DELETE /api/v1/admin/sessions/* -- Admin Dashboard "view active
sessions" + force-revoke any user's session (e.g. responding to a
reported account compromise). Distinct from
GET/DELETE /api/v1/auth/sessions, which only ever operates on the
calling user's own sessions.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.admin.audit_log import record_admin_action
from src.admin.exceptions import AdminUserNotFoundError
from src.api.schemas.admin import AdminSessionListOut, AdminSessionOut
from src.auth.exceptions import SessionNotFoundError
from src.auth.rbac import require_staff_role
from src.auth.repository import AuthRepository
from src.auth.token_store import delete_refresh_session
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

router = APIRouter(prefix="/api/v1/admin/sessions", tags=["admin"])

_repository = AuthRepository()


def _client_ip(request: Request) -> "str | None":
    return request.client.host if request.client else None


@router.get("", response_model=AdminSessionListOut)
def list_active_sessions(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminSessionListOut:
    total, sessions = _repository.list_all_active_sessions(session, limit=limit, offset=offset)
    return AdminSessionListOut(total=total, sessions=[AdminSessionOut.model_validate(s) for s in sessions])


@router.get("/user/{user_id}", response_model=AdminSessionListOut)
def list_sessions_for_user(
    user_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminSessionListOut:
    if _repository.get_user_by_id(session, user_id) is None:
        raise AdminUserNotFoundError(f"No user {user_id}.")
    sessions = _repository.list_active_sessions_for_user(session, user_id)
    return AdminSessionListOut(total=len(sessions), sessions=[AdminSessionOut.model_validate(s) for s in sessions])


@router.delete("/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> dict:
    user_session = _repository.get_user_session_by_id(session, session_id)
    if user_session is None:
        raise SessionNotFoundError(f"No session {session_id}.")

    _repository.revoke_user_session(session, user_session.id)
    delete_refresh_session(user_session.refresh_token_jti)
    record_admin_action(
        session,
        current_user.id,
        "session.admin_revoke",
        "user_session",
        target_id=session_id,
        details={"user_id": user_session.user_id},
        ip_address=_client_ip(request),
    )
    return {"message": f"Session {session_id} revoked."}
