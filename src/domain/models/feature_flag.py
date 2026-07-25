"""FeatureFlag: a runtime-mutable on/off switch an admin can toggle
without a deploy -- distinct from Settings (src/core/config/settings.py),
which is env-level and requires a process restart to change."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    description = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<FeatureFlag key={self.key!r} enabled={self.enabled}>"
