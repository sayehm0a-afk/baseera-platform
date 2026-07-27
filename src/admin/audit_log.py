"""record_admin_action(): the one place every admin/staff action gets
written to AuditLog -- what the Admin Dashboard's "view logs" (Phase
10) reads back. `action` is a dotted string (e.g. "user.suspend",
"subscription.extend_trial") so it stays both human-readable and
groupable without a migration for every new admin action type.
"""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.core.monitoring.prometheus_metrics import get_metrics
from src.domain.models import AuditLog


def list_admin_actions(
    session: Session,
    limit: int,
    offset: int,
    actor_user_id: Optional[int] = None,
    action: Optional[str] = None,
) -> Tuple[int, List[AuditLog]]:
    query = session.query(AuditLog)
    if actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    query = query.order_by(AuditLog.created_at.desc())
    total = query.count()
    return total, query.offset(offset).limit(limit).all()


def record_admin_action(
    session: Session,
    actor_user_id: int,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details_json=details,
        ip_address=ip_address,
    )
    session.add(log)
    session.commit()
    get_metrics().record_admin_action(action)
    return log
