"""GET/PATCH /api/v1/notifications -- the authenticated user's own
notification feed (RADAR-C Phase I). `Notification` rows are already
written by `PortfolioNewsAlertEngine`/`WatchlistNewsAlertEngine`; this
is the first route that reads them back or marks them read. Every
route resolves rows strictly by `current_user.id`, mirroring
`watchlist.py`'s own IDOR-avoidance pattern -- there is no parameter
through which one user could ever name another user's notification.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.api.exceptions import NotificationNotFoundError
from src.api.schemas.auth import MessageOut
from src.api.schemas.notification import NotificationListOut, NotificationOut
from src.core.db.database import get_db
from src.domain.models import Notification, User

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, type=n.type.value, title=n.title, body=n.body, title_ar=n.title_ar, body_ar=n.body_ar,
        read_at=n.read_at, created_at=n.created_at,
    )


@router.get("", response_model=NotificationListOut)
def list_notifications(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationListOut:
    rows = (
        session.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    unread_count = (
        session.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .count()
    )
    return NotificationListOut(notifications=[_out(n) for n in rows], unread_count=unread_count)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationOut:
    notification = (
        session.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if notification is None:
        raise NotificationNotFoundError(f"لا يوجد إشعار بالمعرّف '{notification_id}'.")

    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        session.commit()
    return _out(notification)


@router.post("/read-all", response_model=MessageOut)
def mark_all_notifications_read(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    now = datetime.now(timezone.utc)
    updated = (
        session.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .update({Notification.read_at: now}, synchronize_session=False)
    )
    session.commit()
    return MessageOut(message=f"تم تعليم {updated} إشعار كمقروء.")
