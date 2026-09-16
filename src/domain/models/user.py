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

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, Integer, String, UniqueConstraint
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

    # Optional TOTP 2FA (governance audit 2026-09-11, item 7) -- opt-in
    # only, see src.auth.mfa_totp's module docstring. `mfa_enabled`
    # defaults False for every account, old and new, so nothing about an
    # existing login changes until a staff member deliberately finishes
    # enrollment. `mfa_secret_encrypted` is only ever populated once
    # enrollment is CONFIRMED (a real code verified against it) --
    # `mfa_pending_secret_encrypted` holds a freshly generated secret
    # between "setup" and "activate" so an abandoned/never-confirmed
    # enrollment attempt can never silently enable 2FA.
    mfa_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    mfa_secret_encrypted = Column(String(255), nullable=True)
    mfa_pending_secret_encrypted = Column(String(255), nullable=True)
    mfa_enabled_at = Column(DateTime(timezone=True), nullable=True)

    # 2026-09-16 audit finding: verify_totp_code's valid_window=1 accepts
    # a code for ~90s, but nothing recorded "this account already used
    # this step" -- a code captured in transit/shoulder-surfed/leaked
    # from a compromised authenticator screenshot could be replayed more
    # than once within that window. Set to the matched counter step
    # (src.auth.mfa_totp.get_matching_totp_step) on every accepted TOTP
    # use (enrollment confirmation and login); a later code whose step is
    # <= this value is rejected as a replay even though it's still
    # numerically "valid" per RFC 6238's own step math.
    mfa_last_used_totp_step = Column(BigInteger, nullable=True)

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
    mfa_backup_codes = relationship("MfaBackupCode", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship(
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} is_staff={self.is_staff}>"
