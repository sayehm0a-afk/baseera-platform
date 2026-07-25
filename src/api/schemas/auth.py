"""Request/response schemas for /api/v1/auth/*.

Access and refresh tokens never appear in any of these bodies -- they
travel exclusively as httpOnly cookies (see src/api/routes/auth.py) so
they can never end up in a browser's JS-visible state, a log line that
serializes a response body, or (accidentally) in a frontend Redux/
localStorage store the way the old temp-auth-service.ts stub worked.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


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
    expires_at: datetime
    is_current: bool = False


class MessageOut(BaseModel):
    message: str
