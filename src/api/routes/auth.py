"""POST/GET /api/v1/auth/* -- registration, email verification, login,
refresh, logout, forgot/reset password, "who am I," and device-session
management.

Access and refresh tokens are set as httpOnly cookies here and nowhere
else is a raw token ever put in a JSON response body (see
src/api/schemas/auth.py's docstring). `csrf_token` is a non-httpOnly
double-submit cookie, refreshed alongside the session on every
login/refresh -- verifying it against an `X-CSRF-Token` header on
mutating requests is CSRF middleware wired in M10.10; this milestone
only establishes the cookie so that middleware has something to check
against from day one.

Rate limiting (slowapi, Redis-backed -- see
src/api/middleware/rate_limiting.py) is applied to every brute-force/
enumeration/abuse surface: register, verify-email, login, refresh,
forgot-password, reset-password.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.api.middleware.rate_limiting import limiter
from src.api.schemas.auth import (
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageOut,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    UserOut,
    VerifyEmailRequest,
)
from src.auth import data_export_service, email_verification_service, password_reset_service, session_service, user_service
from src.auth.exceptions import InvalidOrExpiredTokenError, SessionNotFoundError
from src.auth.jwt_service import InvalidAccessTokenError, decode_access_token
from src.auth.repository import AuthRepository
from src.auth.session_service import SessionPair
from src.auth.token_hashing import generate_token, hash_token
from src.auth.token_store import delete_refresh_session, revoke_access_token
from src.core.config import settings
from src.core.db.database import get_db
from src.domain.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_repository = AuthRepository()

_ACCESS_COOKIE = "access_token"
_REFRESH_COOKIE = "refresh_token"
_CSRF_COOKIE = "csrf_token"
_AUTH_COOKIE_PATH = "/api/v1/auth"


def _set_session_cookies(response: Response, pair: SessionPair) -> None:
    secure = settings.is_production
    response.set_cookie(
        _ACCESS_COOKIE,
        pair.access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        _REFRESH_COOKIE,
        pair.refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=_AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        _CSRF_COOKIE,
        generate_token(),
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(_ACCESS_COOKIE, path="/")
    response.delete_cookie(_REFRESH_COOKIE, path=_AUTH_COOKIE_PATH)
    response.delete_cookie(_CSRF_COOKIE, path="/")


def _client_ip(request: Request) -> "str | None":
    return request.client.host if request.client else None


def _revoke_current_access_token_if_present(request: Request) -> None:
    """Best-effort instant revocation of the access token the calling
    browser presented on *this* request -- the one case where we can
    revoke a specific access token immediately (see
    src/auth/token_store.py's docstring for why this isn't done for
    every token everywhere)."""
    raw_access_token = request.cookies.get(_ACCESS_COOKIE)
    if not raw_access_token:
        return
    try:
        claims = decode_access_token(raw_access_token)
    except InvalidAccessTokenError:
        return  # Already expired/malformed -- no explicit revocation needed.
    revoke_access_token(claims["jti"], claims["exp"] - claims["iat"])


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest, session: Session = Depends(get_db)) -> UserOut:
    user = user_service.register(session, body.email, body.password, body.full_name)
    return UserOut.model_validate(user)


@router.post("/verify-email", response_model=UserOut)
@limiter.limit("10/minute")
def verify_email(request: Request, body: VerifyEmailRequest, session: Session = Depends(get_db)) -> UserOut:
    user = email_verification_service.verify_email(session, body.token)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> UserOut:
    user = user_service.authenticate(session, body.email, body.password)
    device_label = request.headers.get("user-agent")
    pair = session_service.create_session(session, user, device_label=device_label, ip_address=_client_ip(request))
    _set_session_cookies(response, pair)
    return UserOut.model_validate(user)


@router.post("/refresh", response_model=MessageOut)
@limiter.limit("30/minute")
def refresh(request: Request, response: Response, session: Session = Depends(get_db)) -> MessageOut:
    raw_refresh_token = request.cookies.get(_REFRESH_COOKIE)
    if not raw_refresh_token:
        raise InvalidOrExpiredTokenError("No refresh token was presented.")

    pair = session_service.refresh_session(session, raw_refresh_token)
    _set_session_cookies(response, pair)
    return MessageOut(message="Session refreshed.")


@router.post("/logout", response_model=MessageOut)
def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> MessageOut:
    _revoke_current_access_token_if_present(request)

    raw_refresh_token = request.cookies.get(_REFRESH_COOKIE)
    if raw_refresh_token:
        session_service.revoke_session(session, raw_refresh_token)

    _clear_session_cookies(response)
    return MessageOut(message="Logged out.")


@router.post("/logout-all", response_model=MessageOut)
def logout_all(
    response: Response,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    session_service.revoke_all_sessions(session, current_user.id)
    _clear_session_cookies(response)
    return MessageOut(message="Logged out of all devices.")


@router.post("/forgot-password", response_model=MessageOut)
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest, session: Session = Depends(get_db)) -> MessageOut:
    # Always returns the same generic message regardless of whether the
    # email is registered -- responding differently would let a caller
    # enumerate which addresses have an account.
    user = _repository.get_user_by_email(session, body.email.strip().lower())
    if user is not None and user.is_active:
        password_reset_service.issue_reset_token(session, user)
    return MessageOut(message="If that email address is registered, a password reset link has been sent.")


@router.post("/reset-password", response_model=MessageOut)
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetPasswordRequest, session: Session = Depends(get_db)) -> MessageOut:
    password_reset_service.reset_password(session, body.token, body.new_password)
    return MessageOut(message="Password has been reset. Please sign in again.")


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/me/export")
@limiter.limit("5/minute")
def export_own_data(
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return data_export_service.build_user_data_export(session, current_user)


@router.delete("/me", response_model=MessageOut)
@limiter.limit("5/minute")
def delete_own_account(
    request: Request,
    body: DeleteAccountRequest,
    response: Response,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    user_service.delete_own_account(session, current_user, body.password)
    _clear_session_cookies(response)
    return MessageOut(message="Account deleted.")


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SessionOut]:
    raw_refresh_token = request.cookies.get(_REFRESH_COOKIE)
    current_jti = hash_token(raw_refresh_token) if raw_refresh_token else None

    sessions = session_service.list_sessions(session, current_user.id)
    return [
        SessionOut(
            id=s.id,
            device_label=s.device_label,
            ip_address=s.ip_address,
            issued_at=s.issued_at,
            last_used_at=s.last_used_at,
            expires_at=s.expires_at,
            is_current=(s.refresh_token_jti == current_jti),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=MessageOut)
def revoke_session(
    request: Request,
    session_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    user_session = _repository.get_user_session_by_id(session, session_id)
    if user_session is None or user_session.user_id != current_user.id:
        raise SessionNotFoundError(f"No session {session_id} for the current user.")

    _repository.revoke_user_session(session, user_session.id)
    delete_refresh_session(user_session.refresh_token_jti)

    # Revoking a *different* device's session can only stop its future
    # refreshes (its already-issued access token has no per-token
    # revocation path here -- see token_store.py). Revoking the calling
    # device's own current session, though, is indistinguishable from
    # a normal logout, so it gets the same instant access-token kill.
    raw_refresh_token = request.cookies.get(_REFRESH_COOKIE)
    if raw_refresh_token and hash_token(raw_refresh_token) == user_session.refresh_token_jti:
        _revoke_current_access_token_if_present(request)

    return MessageOut(message="Session revoked.")
