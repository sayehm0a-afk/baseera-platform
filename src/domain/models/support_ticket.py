"""SupportTicket: a single subject+message+status record -- no
threaded-reply child table yet (Phase 10 plan decision 15); add one
later if/when the support UI needs threading. `assigned_staff_user_id`
is nullable (unassigned until a staff member picks it up)."""

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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_staff_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

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
