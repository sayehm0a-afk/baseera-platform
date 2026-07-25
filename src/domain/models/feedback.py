"""Feedback: a lightweight, unstructured message a user (or a
not-yet-registered visitor -- `user_id` is nullable) submits about the
product. `page_context` records where in the app it was submitted
from, for triage -- free text, not an enum, since the set of pages
changes far more often than this schema should."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class FeedbackCategory(str, enum.Enum):
    BUG = "BUG"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    GENERAL = "GENERAL"


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    category = Column(Enum(FeedbackCategory), nullable=False)
    message = Column(Text, nullable=False)
    page_context = Column(String(255), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} category={self.category}>"
