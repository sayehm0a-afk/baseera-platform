"""Notification: a per-user message -- distinct from Announcement
(platform-wide, admin-authored). `read_at` (nullable) is the
unread/read marker; a Notification is never deleted on read, only
marked."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class NotificationType(str, enum.Enum):
    SYSTEM = "SYSTEM"
    SUBSCRIPTION = "SUBSCRIPTION"
    PORTFOLIO_ALERT = "PORTFOLIO_ALERT"
    MARKET_ALERT = "MARKET_ALERT"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} type={self.type}>"
