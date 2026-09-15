"""MfaBackupCode: one-time recovery codes for a staff account's optional
TOTP 2FA (governance audit 2026-09-11, item 7).

Same "generate high-entropy value, persist only its hash" discipline as
every other bearer-token type this codebase issues (see
src.auth.token_hashing) -- `code_hash` is the only thing ever stored, and
a leaked row hands out nothing usable. `used_at` is set (never the row
deleted) the moment a code is redeemed, so a stolen-and-reused code is
rejected and the account's real usage history stays inspectable, mirroring
`RecommendationOutcome`/`AuditLog`'s own "never delete, mark instead"
convention.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class MfaBackupCode(Base):
    __tablename__ = "mfa_backup_codes"
    __table_args__ = (UniqueConstraint("user_id", "code_hash", name="uq_mfa_backup_code_user_hash"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, index=True)

    used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    user = relationship("User", back_populates="mfa_backup_codes")

    def __repr__(self) -> str:
        return f"<MfaBackupCode user_id={self.user_id!r} used={self.used_at is not None}>"
