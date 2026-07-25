"""UserSession: the durable record backing device/session tracking and
refresh-token rotation.

Redis (src.auth.token_store) is the fast-path lookup for "is this refresh
token currently valid" -- this table is the source of truth: it survives a
Redis flush, and it's what "view active sessions" (both the user's own
`GET /auth/sessions` and the admin `GET /api/v1/admin/sessions`) actually
reads, since Redis alone isn't queryable that way.

`family_id` groups every refresh token descended from one login into a
rotation chain -- refresh-token rotation-with-reuse-detection (every
`/auth/refresh` call issues a new token and revokes the old one) needs a
way to revoke the *entire* chain the moment an already-rotated-away token
is presented again (the standard stolen-refresh-token defense), and
`family_id` is exactly that grouping key.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (UniqueConstraint("refresh_token_jti", name="uq_user_session_refresh_token_jti"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_jti = Column(String(64), nullable=False, index=True)
    family_id = Column(String(64), nullable=False, index=True)

    device_label = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)

    issued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id} family_id={self.family_id!r}>"
