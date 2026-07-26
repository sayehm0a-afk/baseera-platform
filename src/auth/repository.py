"""AuthRepository: the only module that reads/writes this layer's
domain tables (`User`, `UserSession`, `EmailVerificationToken`,
`PasswordResetToken`) -- the same "engines/services compute or
orchestrate, a thin repository persists" separation
`src.portfolio_intelligence.repository.PortfolioRepository` already
establishes.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.domain.models import EmailVerificationToken, PasswordResetToken, StaffRole, User, UserSession


class AuthRepository:
    # --- User ------------------------------------------------------------

    def get_user_by_email(self, session: Session, email: str) -> Optional[User]:
        return session.query(User).filter(User.email == email).one_or_none()

    def get_user_by_id(self, session: Session, user_id: int) -> Optional[User]:
        return session.query(User).filter_by(id=user_id).one_or_none()

    def create_user(
        self, session: Session, email: str, password_hash: str, full_name: Optional[str] = None
    ) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        session.add(user)
        session.commit()
        return user

    def set_email_verified(self, session: Session, user_id: int) -> None:
        session.query(User).filter_by(id=user_id).update({"is_email_verified": True})
        session.commit()

    def set_password_hash(self, session: Session, user_id: int, password_hash: str) -> None:
        session.query(User).filter_by(id=user_id).update({"password_hash": password_hash})
        session.commit()

    def set_is_active(self, session: Session, user_id: int, is_active: bool) -> None:
        session.query(User).filter_by(id=user_id).update({"is_active": is_active})
        session.commit()

    def set_staff_role(self, session: Session, user_id: int, is_staff: bool, staff_role: Optional[StaffRole]) -> None:
        session.query(User).filter_by(id=user_id).update({"is_staff": is_staff, "staff_role": staff_role})
        session.commit()

    def record_login(self, session: Session, user_id: int) -> None:
        session.query(User).filter_by(id=user_id).update(
            {"last_login_at": datetime.now(timezone.utc), "failed_login_attempts": 0, "locked_until": None}
        )
        session.commit()

    def record_failed_login(self, session: Session, user_id: int, lockout_threshold: int, lockout_duration_minutes: int) -> None:
        """Increments the failure counter; once it reaches
        `lockout_threshold`, sets `locked_until` and resets the counter
        so a subsequent lockout requires the same number of fresh
        failures again, rather than an ever-growing count."""
        user = session.query(User).filter_by(id=user_id).one_or_none()
        if user is None:
            return
        attempts = user.failed_login_attempts + 1
        values = {"failed_login_attempts": attempts}
        if attempts >= lockout_threshold:
            values["failed_login_attempts"] = 0
            values["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=lockout_duration_minutes)
        session.query(User).filter_by(id=user_id).update(values)
        session.commit()

    def invalidate_all_access_tokens(self, session: Session, user_id: int) -> None:
        """See User.tokens_invalid_before's docstring -- the O(1)
        instant-kill for every access token ever issued to this user,
        used alongside session revocation."""
        session.query(User).filter_by(id=user_id).update({"tokens_invalid_before": datetime.now(timezone.utc)})
        session.commit()

    def list_users(self, session: Session, limit: int, offset: int) -> "tuple[int, List[User]]":
        query = session.query(User).order_by(User.id)
        total = query.count()
        return total, query.offset(offset).limit(limit).all()

    def delete_user(self, session: Session, user_id: int) -> None:
        """Hard delete via `session.delete()` (not a bulk `Query.delete()`)
        so User's configured relationship cascades (sessions,
        subscription) actually run. Distinct from `set_is_active(...,
        False)` (suspend), which keeps the row for audit/billing
        history -- this is the stronger, admin/OWNER-only action (see
        src/api/routes/admin/users.py). Deliberately has no special
        handling for FK violations from other tables (invoices, audit
        logs, portfolios, ...): the database's own RESTRICT correctly
        blocks deleting a user with real financial/audit history, and
        the caller surfaces that as a clear error rather than silently
        cascading away records that must be retained, or silently
        succeeding while leaving orphaned data."""
        user = session.query(User).filter_by(id=user_id).one_or_none()
        if user is not None:
            session.delete(user)
            session.commit()

    # --- EmailVerificationToken ----------------------------------------

    def create_email_verification_token(
        self, session: Session, user_id: int, token_hash: str, expires_at: datetime
    ) -> EmailVerificationToken:
        token = EmailVerificationToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        session.add(token)
        session.commit()
        return token

    def get_email_verification_token_by_hash(
        self, session: Session, token_hash: str
    ) -> Optional[EmailVerificationToken]:
        return session.query(EmailVerificationToken).filter_by(token_hash=token_hash).one_or_none()

    def consume_email_verification_token(self, session: Session, token_id: int) -> None:
        session.query(EmailVerificationToken).filter_by(id=token_id).update(
            {"consumed_at": datetime.now(timezone.utc)}
        )
        session.commit()

    # --- PasswordResetToken -----------------------------------------------

    def create_password_reset_token(
        self, session: Session, user_id: int, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        token = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        session.add(token)
        session.commit()
        return token

    def get_password_reset_token_by_hash(self, session: Session, token_hash: str) -> Optional[PasswordResetToken]:
        return session.query(PasswordResetToken).filter_by(token_hash=token_hash).one_or_none()

    def consume_password_reset_token(self, session: Session, token_id: int) -> None:
        session.query(PasswordResetToken).filter_by(id=token_id).update(
            {"consumed_at": datetime.now(timezone.utc)}
        )
        session.commit()

    # --- UserSession ------------------------------------------------------

    def create_user_session(
        self,
        session: Session,
        user_id: int,
        refresh_token_jti: str,
        family_id: str,
        expires_at: datetime,
        device_label: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> UserSession:
        user_session = UserSession(
            user_id=user_id,
            refresh_token_jti=refresh_token_jti,
            family_id=family_id,
            expires_at=expires_at,
            device_label=device_label,
            ip_address=ip_address,
        )
        session.add(user_session)
        session.commit()
        return user_session

    def get_user_session_by_jti(self, session: Session, refresh_token_jti: str) -> Optional[UserSession]:
        return session.query(UserSession).filter_by(refresh_token_jti=refresh_token_jti).one_or_none()

    def get_user_session_by_id(self, session: Session, session_id: int) -> Optional[UserSession]:
        return session.query(UserSession).filter_by(id=session_id).one_or_none()

    def revoke_user_session(self, session: Session, session_id: int) -> None:
        session.query(UserSession).filter_by(id=session_id).update({"revoked_at": datetime.now(timezone.utc)})
        session.commit()

    def revoke_session_family(self, session: Session, family_id: str) -> None:
        """The stolen-refresh-token defense: revokes every session
        descended from one login in one call, used when an
        already-rotated-away refresh token is presented again."""
        session.query(UserSession).filter_by(family_id=family_id, revoked_at=None).update(
            {"revoked_at": datetime.now(timezone.utc)}
        )
        session.commit()

    def revoke_all_sessions_for_user(self, session: Session, user_id: int) -> None:
        session.query(UserSession).filter_by(user_id=user_id, revoked_at=None).update(
            {"revoked_at": datetime.now(timezone.utc)}
        )
        session.commit()

    def list_active_sessions_for_user(self, session: Session, user_id: int) -> List[UserSession]:
        now = datetime.now(timezone.utc)
        return (
            session.query(UserSession)
            .filter(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.issued_at.desc())
            .all()
        )

    def list_all_active_sessions(self, session: Session, limit: int, offset: int) -> "tuple[int, List[UserSession]]":
        """For the admin `GET /api/v1/admin/sessions` endpoint."""
        now = datetime.now(timezone.utc)
        query = session.query(UserSession).filter(
            UserSession.revoked_at.is_(None), UserSession.expires_at > now
        )
        total = query.count()
        rows = query.order_by(UserSession.issued_at.desc()).offset(offset).limit(limit).all()
        return total, rows
