"""MfaService: business rules for optional staff TOTP 2FA (governance
audit `docs/governance/تدقيق_شامل_للمنصة_2026-09-11.md`, item 7) -- same
"business rules in one service, persistence in one repository" split
`user_service.py` already follows.

Enrollment is two steps (`start_enrollment` then `confirm_enrollment`) so
a secret is never active until a real code generated from it has been
verified -- a client that generates a QR code but never actually scans it
(or scans it wrong) leaves the account exactly as it was, never locked
into an unusable 2FA state.
"""

from typing import List, Tuple

from sqlalchemy.orm import Session

from src.auth import mfa_totp
from src.auth.exceptions import (
    InvalidCredentialsError,
    InvalidMfaCodeError,
    MfaAlreadyEnabledError,
    MfaNotEnabledError,
    MfaSetupNotStartedError,
)
from src.auth.password_hashing import verify_password
from src.auth.repository import AuthRepository
from src.auth.token_hashing import hash_token
from src.domain.models import User

_repository = AuthRepository()


def start_enrollment(session: Session, user: User) -> Tuple[str, str]:
    """Returns (secret, provisioning_uri). Overwrites any previous,
    never-confirmed pending secret -- a caller who abandoned an earlier
    enrollment attempt and calls this again gets a clean, fresh one
    rather than being stuck with whichever QR code they last saw."""
    if user.mfa_enabled:
        raise MfaAlreadyEnabledError("2FA is already enabled on this account. Disable it before re-enrolling.")

    secret = mfa_totp.generate_totp_secret()
    encrypted = mfa_totp.encrypt_secret(secret)
    _repository.set_mfa_pending_secret(session, user.id, encrypted)
    return secret, mfa_totp.provisioning_uri(secret, user.email)


def confirm_enrollment(session: Session, user: User, code: str) -> List[str]:
    """Verifies `code` against the pending secret and, on success,
    activates 2FA and returns a fresh set of RAW backup codes -- the only
    moment they are ever available in plaintext; only their hashes are
    persisted (`src.auth.token_hashing`)."""
    if user.mfa_enabled:
        raise MfaAlreadyEnabledError("2FA is already enabled on this account.")
    if not user.mfa_pending_secret_encrypted:
        raise MfaSetupNotStartedError("No MFA enrollment is in progress. Call /mfa/setup first.")

    pending_secret = mfa_totp.decrypt_secret(user.mfa_pending_secret_encrypted)
    step = mfa_totp.get_matching_totp_step(pending_secret, code)
    if step is None:
        raise InvalidMfaCodeError("The code did not match. Check your authenticator app and try again.")

    backup_codes = mfa_totp.generate_backup_codes()
    _repository.replace_backup_codes(session, user.id, [hash_token(c) for c in backup_codes])
    _repository.activate_mfa(session, user.id, user.mfa_pending_secret_encrypted)
    # Record the step the confirmation code itself used -- otherwise the
    # same code (still within its +/-1 step window) could immediately be
    # replayed against /mfa/login-verify right after enrollment.
    _repository.record_mfa_totp_step(session, user.id, step)
    return backup_codes


def disable_mfa(session: Session, user: User, password: str) -> None:
    if not user.mfa_enabled:
        raise MfaNotEnabledError("2FA is not enabled on this account.")
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Password is incorrect.")
    _repository.disable_mfa(session, user.id)


def regenerate_backup_codes(session: Session, user: User, password: str) -> List[str]:
    """Invalidates every existing backup code (used or not) and issues a
    fresh set -- the standard response to "I think my old codes leaked"
    without having to fully disable/re-enroll TOTP itself."""
    if not user.mfa_enabled:
        raise MfaNotEnabledError("2FA is not enabled on this account.")
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Password is incorrect.")

    backup_codes = mfa_totp.generate_backup_codes()
    _repository.replace_backup_codes(session, user.id, [hash_token(c) for c in backup_codes])
    return backup_codes


def verify_login_code(session: Session, user: User, code: str) -> bool:
    """Tries the code as a TOTP code first, then as a one-time backup
    code -- the client never has to say which kind it is. A matched
    backup code is marked used (never deleted, never reusable) before
    returning True. A TOTP code whose matched step was already accepted
    before (User.mfa_last_used_totp_step) is rejected as a replay even
    though it's still within its own +/-1 step drift window."""
    if user.mfa_secret_encrypted:
        secret = mfa_totp.decrypt_secret(user.mfa_secret_encrypted)
        step = mfa_totp.get_matching_totp_step(secret, code)
        if step is not None and (user.mfa_last_used_totp_step is None or step > user.mfa_last_used_totp_step):
            _repository.record_mfa_totp_step(session, user.id, step)
            return True

    code_hash = hash_token(code)
    for backup_code in _repository.get_unused_backup_codes(session, user.id):
        if backup_code.code_hash == code_hash:
            _repository.mark_backup_code_used(session, backup_code.id)
            return True

    return False
