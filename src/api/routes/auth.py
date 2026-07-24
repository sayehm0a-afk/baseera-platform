"""POST /auth/login, POST /auth/refresh

Issues/refreshes JWTs for the single configured admin account (see
src/api/auth/__init__.py for why there is no multi-user table yet).
No UI, no frontend -- pure token issuance, per explicit instruction.
"""

import hmac

from fastapi import APIRouter

from src.api import config
from src.api.auth.jwt_handler import JWTError, create_access_token, create_refresh_token, decode_token_of_type
from src.api.auth.password import verify_password
from src.api.exceptions import UnauthorizedError
from src.api.schemas.auth import AccessTokenResponse, LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest) -> TokenResponse:
    configured_username = config.get_admin_username()
    configured_hash = config.get_admin_password_hash()
    secret = config.get_jwt_secret()

    username_matches = bool(configured_username) and hmac.compare_digest(
        credentials.username, configured_username
    )
    if not username_matches or not verify_password(credentials.password, configured_hash, secret):
        raise UnauthorizedError("Invalid username or password")

    access_expires_in = config.get_access_token_expire_seconds()
    refresh_expires_in = config.get_refresh_token_expire_seconds()
    return TokenResponse(
        access_token=create_access_token(credentials.username, secret, access_expires_in),
        refresh_token=create_refresh_token(credentials.username, secret, refresh_expires_in),
        expires_in=access_expires_in,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(payload: RefreshRequest) -> AccessTokenResponse:
    secret = config.get_jwt_secret()
    try:
        claims = decode_token_of_type(payload.refresh_token, secret, expected_type="refresh")
    except JWTError as exc:
        raise UnauthorizedError(f"Invalid or expired refresh token: {exc}") from exc

    access_expires_in = config.get_access_token_expire_seconds()
    return AccessTokenResponse(
        access_token=create_access_token(claims["sub"], secret, access_expires_in),
        expires_in=access_expires_in,
    )
