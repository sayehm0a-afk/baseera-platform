"""Request/response schemas for /api/v1/auth/*.

Access and refresh tokens never appear in any of these bodies -- they
travel exclusively as httpOnly cookies (see src/api/routes/auth.py) so
they can never end up in a browser's JS-visible state, a log line that
serializes a response body, or (accidentally) in a frontend Redux/
localStorage store the way the old temp-auth-service.ts stub worked.
"""

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# 2026-09 audit finding: length alone (min_length=8) let a purely
# repeated/sequential password like "aaaaaaaa" or "12345678" through --
# only ever applied to a NEW password (registration, reset), never to
# LoginRequest, so no existing account's ability to log in is affected.
# Deliberately mild (letter + digit, not a symbol/case mix) to stay
# usable for a mainstream, possibly non-technical user base while still
# closing the all-one-character-class gap.
_HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_HAS_DIGIT_RE = re.compile(r"\d")


def _validate_password_complexity(value: str) -> str:
    if not _HAS_LETTER_RE.search(value) or not _HAS_DIGIT_RE.search(value):
        raise ValueError("password_must_contain_letter_and_digit")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: Optional[str] = None

    _validate_password = field_validator("password")(_validate_password_complexity)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)

    _validate_new_password = field_validator("new_password")(_validate_password_complexity)


class DeleteAccountRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    is_email_verified: bool
    is_staff: bool
    staff_role: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_label: Optional[str] = None
    ip_address: Optional[str] = None
    issued_at: datetime
    last_used_at: datetime
    expires_at: datetime
    is_current: bool = False


class MessageOut(BaseModel):
    message: str
