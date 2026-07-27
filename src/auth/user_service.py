"""UserService: the one place registration/login business rules live --
mirrors the "business rules in one service, persistence in one
repository" split every other package in this codebase already uses
(e.g. PortfolioEngine vs. PortfolioRepository).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.auth import email_verification_service
from src.auth.exceptions import (
    AccountHasBillingHistoryError,
    AccountLockedError,
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    StaffAccountSelfDeletionError,
)
from src.auth.password_hashing import hash_password, verify_password
from src.auth.repository import AuthRepository
from src.core.config import settings
from src.core.monitoring.prometheus_metrics import get_metrics
from src.domain.models import User
from src.subscriptions import subscription_service

logger = logging.getLogger(__name__)

_repository = AuthRepository()

# A real, precomputed bcrypt hash of a value no live password will ever
# equal -- used to run a full password verification even when no user
# was found, so an attacker cannot distinguish "no such account" from
# "wrong password" by response timing (bcrypt is deliberately slow;
# skipping it via short-circuit evaluation for a nonexistent user would
# make the "no such account" response measurably faster).
_DUMMY_PASSWORD_HASH = hash_password("baseerah-timing-normalization-dummy-value")


def _is_locked(user: User) -> bool:
    if user.locked_until is None:
        return False
    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > datetime.now(timezone.utc)


def register(session: Session, email: str, password: str, full_name: "str | None" = None) -> User:
    normalized_email = email.strip().lower()
    if _repository.get_user_by_email(session, normalized_email) is not None:
        raise EmailAlreadyRegisteredError(f"An account with email {normalized_email!r} already exists.")

    user = _repository.create_user(session, normalized_email, hash_password(password), full_name)
    email_verification_service.issue_verification_token(session, user)
    subscription_service.provision_trial_subscription(session, user)
    get_metrics().record_registration()
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    user = _repository.get_user_by_email(session, normalized_email)

    # A currently-locked account is rejected before spending time on a
    # password check -- this is the one place this function's behavior
    # (message + control flow) legitimately differs for an
    # account-that-exists vs. one that doesn't, a disclosed, standard
    # trade-off of account lockout (see AccountLockedError's docstring).
    if user is not None and _is_locked(user):
        get_metrics().record_login("failure")
        raise AccountLockedError(
            "Too many failed login attempts. Please try again later or reset your password."
        )

    # Always run a real bcrypt verification -- against the dummy hash
    # when no user was found -- so this branch's timing can never reveal
    # whether normalized_email belongs to a registered account.
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, password_hash)

    if user is None or not password_ok:
        if user is not None:
            _repository.record_failed_login(
                session, user.id, settings.login_lockout_max_attempts, settings.login_lockout_duration_minutes
            )
        get_metrics().record_login("failure")
        raise InvalidCredentialsError("Email or password is incorrect.")

    if not user.is_active:
        get_metrics().record_login("failure")
        raise AccountSuspendedError("This account has been suspended.")

    if not user.is_email_verified:
        get_metrics().record_login("failure")
        raise EmailNotVerifiedError("Please verify your email address before signing in.")

    _repository.record_login(session, user.id)
    get_metrics().record_login("success")
    return user


def delete_own_account(session: Session, user: User, password: str) -> None:
    """Self-service account deletion (Phase 13 P13.6 -- customer data
    protection): a real password confirmation is required (never just
    "you're logged in, click delete") so a hijacked-but-not-fully-
    compromised browser session (e.g. an unattended unlocked laptop)
    can't be used to destroy the account outright. Hard-deletes via the
    same `AuthRepository.delete_user` the admin OWNER-only route uses,
    including the same FK-RESTRICT-aware handling: a real financial/
    audit history (invoices, audit log entries) blocks the delete
    rather than silently discarding it, surfaced here with
    customer-facing wording pointing at support instead of the
    admin-facing `user_has_related_records` code. Blocked outright for
    any staff account (`is_staff=True`) -- see
    `StaffAccountSelfDeletionError`'s own docstring for why.

    Audit trail: logged via structured application logging (masked by
    `mask_dict_values`, P13.2), not `AuditLog` (the SQL table). AuditLog
    is explicitly scoped to admin/staff actions (see its own docstring)
    and, more fundamentally, `actor_user_id` is a NOT NULL FK to
    `users.id` with no cascade -- a row logging "user X deleted
    themselves" could never coexist with user X's own row actually
    being gone, so it structurally cannot represent this event without
    either violating that FK or weakening the exact RESTRICT guarantee
    P13.4/P13.6 depend on elsewhere. Structured logs have no such
    constraint."""
    user_id = user.id
    logger.info("Self-service account deletion requested.", extra={"extra_fields": {"user_id": user_id}})

    if user.is_staff:
        logger.info(
            "Self-service account deletion blocked -- staff account.",
            extra={"extra_fields": {"user_id": user_id}},
        )
        raise StaffAccountSelfDeletionError(
            "Staff accounts cannot be deleted through self-service. Ask another owner to revoke your "
            "staff access first."
        )

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Password is incorrect.")

    try:
        _repository.delete_user(session, user_id)
    except IntegrityError as exc:
        session.rollback()
        logger.info(
            "Self-service account deletion blocked by retained billing/audit history.",
            extra={"extra_fields": {"user_id": user_id}},
        )
        raise AccountHasBillingHistoryError(
            "This account has billing or audit history and can't be deleted automatically. "
            "Please contact support."
        ) from exc

    logger.info("Self-service account deletion completed.", extra={"extra_fields": {"user_id": user_id}})
