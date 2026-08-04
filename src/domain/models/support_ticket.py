"""SupportTicket: a single subject+message+status record -- no
threaded-reply child table yet (Phase 10 plan decision 15); add one
later if/when the support UI needs threading. `assigned_staff_user_id`
is nullable (unassigned until a staff member picks it up).

`user_id` was made nullable in Phase 13 P13.6: a support conversation's
substance retains value for support-quality review even after the
customer deletes their account, so it is `ON DELETE SET NULL`
(anonymized, not discarded) rather than blocking account deletion the
way real financial/audit records (Invoice, AuditLog) correctly do.
`assigned_staff_user_id` is `ON DELETE SET NULL` for the same reason,
independent of the customer-deletion feature -- a staff member's own
account being deleted must not be blocked by tickets once assigned to
them.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class SupportTicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_staff_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(Enum(SupportTicketStatus), nullable=False, default=SupportTicketStatus.OPEN)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SupportTicket id={self.id} user_id={self.user_id} status={self.status}>"
