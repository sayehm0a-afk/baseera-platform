"""GET/POST/DELETE /api/v1/admin/users/* -- Admin Dashboard user
management: view users, suspend/unsuspend, hard-delete. Every route
requires ADMIN (or OWNER); delete additionally requires OWNER, since
it is the one irreversible action in this file. Every mutating action
is recorded to AuditLog.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.admin.audit_log import record_admin_action
from src.admin.exceptions import AdminUserNotFoundError, CannotModifyOwnStaffRoleError, UserHasRelatedRecordsError
from src.api.schemas.admin import AdminUserListOut, AdminUserOut, SetStaffRoleRequest
from src.auth.rbac import require_staff_role
from src.auth.repository import AuthRepository
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])

_repository = AuthRepository()


def _client_ip(request: Request) -> "str | None":
    return request.client.host if request.client else None


def _get_user_or_404(session: Session, user_id: int) -> User:
    user = _repository.get_user_by_id(session, user_id)
    if user is None:
        raise AdminUserNotFoundError(f"No user {user_id}.")
    return user


@router.get("", response_model=AdminUserListOut)
def list_users(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminUserListOut:
    total, users = _repository.list_users(session, limit=limit, offset=offset)
    return AdminUserListOut(total=total, users=[AdminUserOut.model_validate(u) for u in users])


@router.get("/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminUserOut:
    return AdminUserOut.model_validate(_get_user_or_404(session, user_id))


@router.post("/{user_id}/suspend", response_model=AdminUserOut)
def suspend_user(
    user_id: int,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminUserOut:
    user = _get_user_or_404(session, user_id)
    _repository.set_is_active(session, user.id, False)
    record_admin_action(
        session, current_user.id, "user.suspend", "user", target_id=user.id, ip_address=_client_ip(request)
    )
    return AdminUserOut.model_validate(_get_user_or_404(session, user_id))


@router.post("/{user_id}/unsuspend", response_model=AdminUserOut)
def unsuspend_user(
    user_id: int,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminUserOut:
    user = _get_user_or_404(session, user_id)
    _repository.set_is_active(session, user.id, True)
    record_admin_action(
        session, current_user.id, "user.unsuspend", "user", target_id=user.id, ip_address=_client_ip(request)
    )
    return AdminUserOut.model_validate(_get_user_or_404(session, user_id))


@router.post("/{user_id}/staff-role", response_model=AdminUserOut)
def set_staff_role(
    user_id: int,
    body: SetStaffRoleRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.OWNER)),
) -> AdminUserOut:
    """Grants or revokes staff access. OWNER-only: this is the one route
    that can create another OWNER, so it must require an existing OWNER
    to call it. An OWNER may not change their own row through this route
    (`CannotModifyOwnStaffRoleError`) -- self-service role changes could
    strip every OWNER from the platform in a single call with no path
    back in, since no other route can ever restore OWNER access."""
    user = _get_user_or_404(session, user_id)
    if user.id == current_user.id:
        raise CannotModifyOwnStaffRoleError("You cannot change your own staff role.")

    staff_role = StaffRole(body.staff_role) if body.staff_role is not None else None
    _repository.set_staff_role(session, user.id, body.is_staff, staff_role)
    record_admin_action(
        session,
        current_user.id,
        "user.set_staff_role",
        "user",
        target_id=user.id,
        details={"is_staff": body.is_staff, "staff_role": body.staff_role},
        ip_address=_client_ip(request),
    )
    return AdminUserOut.model_validate(_get_user_or_404(session, user_id))


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.OWNER)),
) -> dict:
    user = _get_user_or_404(session, user_id)
    try:
        _repository.delete_user(session, user.id)
    except IntegrityError as exc:
        session.rollback()
        raise UserHasRelatedRecordsError(
            f"User {user_id} has related records (invoices, audit log entries, etc.) and cannot be "
            "hard-deleted -- suspend the account instead."
        ) from exc
    record_admin_action(
        session, current_user.id, "user.delete", "user", target_id=user_id, ip_address=_client_ip(request)
    )
    return {"message": f"User {user_id} deleted."}
