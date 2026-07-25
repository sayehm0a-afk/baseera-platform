"""GlobalSetting: a runtime-mutable ops toggle/value (key/value string
pair an admin can change without a deploy) -- distinct from both
Settings (env-level, process-restart-required) and FeatureFlag
(boolean on/off specifically)."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<GlobalSetting key={self.key!r}>"
