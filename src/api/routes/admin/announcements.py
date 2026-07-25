"""GET/POST/PATCH /api/v1/admin/announcements/* -- manage platform-wide
announcements. Read is staff-only here (the admin management view);
the customer-facing "what announcements are currently live" surface
is a separate, future, unauthenticated-or-customer-scoped endpoint,
not built in this milestone.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.admin.audit_log import record_admin_action
from src.admin.exceptions import AnnouncementNotFoundError
from src.api.schemas.admin import AnnouncementCreateRequest, AnnouncementListOut, AnnouncementOut, AnnouncementUpdateRequest
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import Announcement, AnnouncementSeverity, StaffRole, User

router = APIRouter(prefix="/api/v1/admin/announcements", tags=["admin"])


def _client_ip(request: Request) -> "str | None":
    return request.client.host if request.client else None


def _get_announcement_or_404(session: Session, announcement_id: int) -> Announcement:
    announcement = session.query(Announcement).filter_by(id=announcement_id).one_or_none()
    if announcement is None:
        raise AnnouncementNotFoundError(f"No announcement {announcement_id}.")
    return announcement


@router.get("", response_model=AnnouncementListOut)
def list_announcements(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> AnnouncementListOut:
    rows = session.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return AnnouncementListOut(announcements=[AnnouncementOut.model_validate(r) for r in rows])


@router.post("", response_model=AnnouncementOut, status_code=201)
def create_announcement(
    body: AnnouncementCreateRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AnnouncementOut:
    announcement = Announcement(
        created_by_user_id=current_user.id,
        title=body.title,
        body=body.body,
        severity=AnnouncementSeverity(body.severity),
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    session.add(announcement)
    session.commit()
    record_admin_action(
        session,
        current_user.id,
        "announcement.create",
        "announcement",
        target_id=announcement.id,
        ip_address=_client_ip(request),
    )
    return AnnouncementOut.model_validate(announcement)


@router.patch("/{announcement_id}", response_model=AnnouncementOut)
def update_announcement(
    announcement_id: int,
    body: AnnouncementUpdateRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AnnouncementOut:
    announcement = _get_announcement_or_404(session, announcement_id)
    if body.is_active is not None:
        announcement.is_active = body.is_active
        session.commit()
    record_admin_action(
        session,
        current_user.id,
        "announcement.update",
        "announcement",
        target_id=announcement_id,
        details={"is_active": body.is_active},
        ip_address=_client_ip(request),
    )
    return AnnouncementOut.model_validate(announcement)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> dict:
    announcement = _get_announcement_or_404(session, announcement_id)
    session.delete(announcement)
    session.commit()
    record_admin_action(
        session, current_user.id, "announcement.delete", "announcement", target_id=announcement_id,
        ip_address=_client_ip(request),
    )
    return {"message": f"Announcement {announcement_id} deleted."}
