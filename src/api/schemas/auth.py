"""Request/response schemas for POST /auth/login and POST /auth/refresh
(src/api/routes/auth.py)."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AccessTokenResponse(BaseModel):
    """POST /auth/refresh only issues a new access token -- the
    presented refresh token remains valid until its own expiry (no
    refresh-token rotation in this foundation; see routes/auth.py)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
