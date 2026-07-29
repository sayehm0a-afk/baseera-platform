"""Announcement: an admin-authored, platform-wide banner/notice with a
scheduling window (`starts_at`/`ends_at`) and severity, distinct from
a per-user Notification -- one Announcement row can be shown to every
customer at once, a Notification is always addressed to one user."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class AnnouncementSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    severity = Column(Enum(AnnouncementSeverity), nullable=False, default=AnnouncementSeverity.INFO)

    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Announcement id={self.id} title={self.title!r} severity={self.severity}>"
