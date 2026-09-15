"""POST /api/v1/auth/mfa/* -- optional TOTP 2FA for OWNER/ADMIN staff
accounts (governance audit `docs/governance/تدقيق_شامل_للمنصة_2026-09-11.md`,
item 7).

Enrollment (`/setup`, `/activate`, `/disable`, `/backup-codes/regenerate`)
is gated behind `require_any_staff_role(OWNER, ADMIN)` -- exactly the
scope the audit item asked for, and the narrowest one that still lets an
account enable this for itself without any admin-on-admin action.
`/login-verify` has no such gate (the caller isn't fully authenticated
yet by definition) -- it is scoped instead by the short-lived
`mfa_token` `POST /auth/login` issues, decoded in
`src.auth.jwt_service.decode_mfa_pending_token`.

`_complete_login` (session creation + cookie-setting) is shared with
`src.api.routes.auth.login` via that module's own helpers so a code-
verified login behaves identically to a password-only one in every way
that matters (session record, cookies, CSRF token, audit-visible device
label) -- this file never duplicates that logic.
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from src.api.middleware.rate_limiting import auth_target_key, enforce_network_ceiling, limiter
from src.api.routes.auth import _complete_login
from src.api.schemas.auth import UserOut
from src.api.schemas.mfa import (
    MfaActivateOut,
    MfaActivateRequest,
    MfaDisableRequest,
    MfaLoginVerifyRequest,
    MfaRegenerateBackupCodesOut,
    MfaRegenerateBackupCodesRequest,
    MfaSetupOut,
)
from src.auth import mfa_service
from src.auth.exceptions import InvalidMfaCodeError, InvalidOrExpiredTokenError
from src.auth.jwt_service import InvalidMfaPendingTokenError, decode_mfa_pending_token
from src.auth.rbac import require_any_staff_role
from src.auth.repository import AuthRepository
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

router = APIRouter(prefix="/api/v1/auth/mfa", tags=["auth"])

_repository = AuthRepository()

_STAFF_MFA_ROLES = (StaffRole.OWNER, StaffRole.ADMIN)


@router.post("/setup", response_model=MfaSetupOut)
def setup_mfa(
    current_user: User = Depends(require_any_staff_role(*_STAFF_MFA_ROLES)),
    session: Session = Depends(get_db),
) -> MfaSetupOut:
    secret, uri = mfa_service.start_enrollment(session, current_user)
    return MfaSetupOut(secret=secret, provisioning_uri=uri)


@router.post("/activate", response_model=MfaActivateOut)
@limiter.limit("10/minute", key_func=auth_target_key)
def activate_mfa(
    request: Request,
    body: MfaActivateRequest,
    current_user: User = Depends(require_any_staff_role(*_STAFF_MFA_ROLES)),
    session: Session = Depends(get_db),
    _network_ceiling: None = Depends(enforce_network_ceiling("mfa-activate", "10/minute")),
) -> MfaActivateOut:
    backup_codes = mfa_service.confirm_enrollment(session, current_user, body.code)
    return MfaActivateOut(backup_codes=backup_codes)


@router.post("/disable", response_model=UserOut)
def disable_mfa(
    body: MfaDisableRequest,
    current_user: User = Depends(require_any_staff_role(*_STAFF_MFA_ROLES)),
    session: Session = Depends(get_db),
) -> UserOut:
    mfa_service.disable_mfa(session, current_user, body.password)
    refreshed = _repository.get_user_by_id(session, current_user.id)
    return UserOut.model_validate(refreshed)


@router.post("/backup-codes/regenerate", response_model=MfaRegenerateBackupCodesOut)
def regenerate_backup_codes(
    body: MfaRegenerateBackupCodesRequest,
    current_user: User = Depends(require_any_staff_role(*_STAFF_MFA_ROLES)),
    session: Session = Depends(get_db),
) -> MfaRegenerateBackupCodesOut:
    backup_codes = mfa_service.regenerate_backup_codes(session, current_user, body.password)
    return MfaRegenerateBackupCodesOut(backup_codes=backup_codes)


@router.post("/login-verify", response_model=UserOut)
@limiter.limit("10/minute", key_func=auth_target_key)
def login_verify(
    request: Request,
    body: MfaLoginVerifyRequest,
    response: Response,
    session: Session = Depends(get_db),
    _network_ceiling: None = Depends(enforce_network_ceiling("mfa-login-verify", "10/minute")),
) -> UserOut:
    try:
        user_id = decode_mfa_pending_token(body.mfa_token)
    except InvalidMfaPendingTokenError as exc:
        raise InvalidOrExpiredTokenError("MFA session has expired. Please log in again.") from exc

    user = _repository.get_user_by_id(session, user_id)
    if user is None or not user.mfa_enabled:
        raise InvalidOrExpiredTokenError("MFA session has expired. Please log in again.")

    if not mfa_service.verify_login_code(session, user, body.code):
        raise InvalidMfaCodeError("The code did not match.")

    return _complete_login(request, response, session, user)
