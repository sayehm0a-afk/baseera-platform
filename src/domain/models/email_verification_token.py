"""EmailVerificationToken: a single-use, expiring token proving control
of the email address a User registered with.

`token_hash` stores a hash of the token, never the raw value -- the same
"a DB leak shouldn't hand out live credentials" discipline password
hashes already apply, here for a bearer token instead of a password.
`consumed_at` makes verification single-use: a second attempt to verify
with an already-used token is a no-op failure, not a repeat success.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db.database import Base


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_email_verification_token_hash"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, index=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<EmailVerificationToken id={self.id} user_id={self.user_id}>"
