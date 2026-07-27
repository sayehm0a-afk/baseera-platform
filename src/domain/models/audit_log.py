"""AuditLog: an immutable record of every admin/staff action (Phase 10
Admin Dashboard's "view logs" -- scored down to querying this table +
AIRequest, not tailing raw log files, which don't survive a container
restart anyway). `action` is a dotted string (e.g. "user.suspend",
"subscription.extend_trial") so it's both human-readable and groupable
without a separate enum that would need a migration for every new
admin action type.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from src.core.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=True)
    details_json = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} actor_user_id={self.actor_user_id} action={self.action!r}>"
