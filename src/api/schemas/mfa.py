"""Schemas for optional staff TOTP 2FA (governance audit 2026-09-11,
item 7) -- enrollment (`/mfa/setup`, `/mfa/activate`, `/mfa/disable`) and
the login-time gate (`/mfa/login-verify`). See src.auth.mfa_totp for the
underlying crypto and src.api.routes.mfa for the routes themselves.
"""

from typing import List

from pydantic import BaseModel, Field


class MfaSetupOut(BaseModel):
    # Base32 secret, for manual entry when a QR scanner isn't available --
    # never logged, never persisted anywhere outside the encrypted
    # `mfa_pending_secret_encrypted` column it was derived from.
    secret: str
    # otpauth:// URI -- the frontend renders this as a QR code for an
    # authenticator app to scan directly.
    provisioning_uri: str


class MfaActivateRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaActivateOut(BaseModel):
    # Shown to the user exactly once -- the server only ever stores
    # each code's hash from this point on (src.auth.token_hashing),
    # never the raw value.
    backup_codes: List[str]


class MfaDisableRequest(BaseModel):
    password: str


class MfaRegenerateBackupCodesRequest(BaseModel):
    password: str


class MfaRegenerateBackupCodesOut(BaseModel):
    backup_codes: List[str]


class MfaRequiredOut(BaseModel):
    """Returned by `POST /auth/login` in place of `UserOut` when the
    password check succeeded but the account has 2FA enabled -- no
    session cookie is set yet. `mfa_token` must be redeemed at
    `POST /auth/mfa/login-verify` (with a real code) within its short
    validity window to actually complete the login."""

    mfa_required: bool = True
    mfa_token: str


class MfaLoginVerifyRequest(BaseModel):
    mfa_token: str
    # A TOTP code (6 digits) or a backup code (10 hex chars) -- the
    # service layer tries both, never asks the client to specify which.
    code: str = Field(min_length=6, max_length=10)
