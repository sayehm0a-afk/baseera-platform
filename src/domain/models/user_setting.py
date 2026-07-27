"""UserSetting: genuinely free-form per-user preferences (theme,
notification toggles, locale, etc.) -- a JSON bag, unlike everywhere
else in this codebase, where each field gets its own named column;
preferences are additive and UI-driven, not something every new key
should need a migration for."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db.database import Base


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_setting_user"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    preferences_json = Column(JSON, nullable=False, default=dict, server_default="{}")

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<UserSetting user_id={self.user_id}>"
