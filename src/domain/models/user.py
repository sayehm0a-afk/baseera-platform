"""User: the root identity for every Baseerah account.

RBAC is deliberately split into two orthogonal concepts, not one flat
role enum: `is_staff`/`staff_role` here answer "who works at Baseerah"
(rare, hand-assigned, changes almost never); "what a customer's account
currently is" (trial/paying/expired) lives entirely on `Subscription.status`
(src/domain/models/subscription.py), never on this model -- conflating the
two would break the moment a subscription is canceled-vs-expired-vs-
past-due independently of any staff concept, or a staff member also wants
a paid subscription of their own.

`is_active` is a soft-suspend flag (admin "suspend user" sets it False)
kept distinct from deletion -- suspending must not lose the row (audit
trail, billing history) the way a hard delete would.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class StaffRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    # ANALYST is deliberately outside the OWNER > ADMIN > SUPPORT rank
    # ladder in src/auth/rbac.py -- see require_any_staff_role. It is
    # granted access to specific read-only AI/market-intelligence audit
    # routes only, never inherited from or into SUPPORT/ADMIN/OWNER.
    ANALYST = "ANALYST"
    SUPPORT = "SUPPORT"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    is_email_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    is_staff = Column(Boolean, nullable=False, default=False, server_default="false")
    staff_role = Column(Enum(StaffRole), nullable=True)

    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Account-level lockout (distinct from src/api/middleware/rate_limiting.py's
    # per-IP rate limit on /auth/login -- an attacker rotating IPs bypasses
    # that but not this). Reset to 0/None on a successful login; see
    # src/auth/user_service.py's `authenticate()` for the exact policy.
    failed_login_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Set (to "now") whenever every session is force-revoked (password
    # reset, "sign out everywhere") -- an access-token JWT is stateless
    # and NOT looked up in Redis/Postgres on the ordinary request path
    # (see src/auth/token_store.py), so revoking a *session* alone
    # cannot kill an already-issued, still-unexpired access token. This
    # column is the O(1) escape hatch: get_current_user rejects any
    # token whose `iat` predates this timestamp, regardless of how many
    # access tokens were ever issued or whether their jtis were tracked.
    tokens_invalid_before = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship(
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} is_staff={self.is_staff}>"
