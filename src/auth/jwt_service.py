"""Access-token JWT encode/decode. Refresh tokens are deliberately NOT
JWTs -- see src/auth/token_store.py's docstring for why (opaque, trivially
revocable-by-lookup tokens are the better fit for something long-lived
and security-critical, whereas the access token is short-lived and
stateless by design: it is never checked against Redis on the common
request path, only its signature and expiry).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from src.core.config import settings

_ALGORITHM = "HS256"


class InvalidAccessTokenError(Exception):
    pass


def encode_access_token(user_id: int, is_staff: bool, staff_role: "str | None") -> str:
    now = datetime.now(timezone.utc)
    claims: Dict[str, Any] = {
        "sub": str(user_id),
        "is_staff": is_staff,
        "staff_role": staff_role,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidAccessTokenError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessTokenError("Access token is malformed or has an invalid signature.") from exc

    if claims.get("type") != "access":
        raise InvalidAccessTokenError("Token is not an access token.")
    return claims


# Deliberately short-lived (minutes, not the access token's own window) and
# a distinct "type" claim -- this token proves only "the password check for
# this user just succeeded," never "this user is authenticated." It is
# never accepted by get_current_user or any other route: only
# src.api.routes.mfa's login-verify endpoint decodes it, and only to look
# up which user is completing a gated login.
_MFA_PENDING_TTL_MINUTES = 5


class InvalidMfaPendingTokenError(Exception):
    pass


def encode_mfa_pending_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    claims: Dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_MFA_PENDING_TTL_MINUTES),
        "type": "mfa_pending",
    }
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM)


def decode_mfa_pending_token(token: str) -> int:
    """Returns the user id it was issued for."""
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise InvalidMfaPendingTokenError("MFA pending token is expired, malformed, or invalid.") from exc

    if claims.get("type") != "mfa_pending":
        raise InvalidMfaPendingTokenError("Token is not an MFA pending token.")
    return int(claims["sub"])
