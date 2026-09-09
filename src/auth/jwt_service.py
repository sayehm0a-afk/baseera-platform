"""Signed short-lived access tokens. Authorization also checks the
current database user, revocation set and (for new tokens) session family
in get_current_user. Refresh tokens remain opaque, hashed credentials.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from src.core.config import settings

_ALGORITHM = "HS256"


class InvalidAccessTokenError(Exception):
    pass


def encode_access_token(
    user_id: int, is_staff: bool, staff_role: "str | None", session_family_id: "str | None" = None
) -> str:
    now = datetime.now(timezone.utc)
    claims: Dict[str, Any] = {
        "sub": str(user_id),
        "is_staff": is_staff,
        "staff_role": staff_role,
        "jti": uuid.uuid4().hex,
        # PyJWT truncates datetime claims to whole seconds. Preserve a
        # fractional NumericDate so a new login after logout-all in the
        # same second is not mistaken for a pre-revocation credential.
        "iat": now.timestamp(),
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    if session_family_id is not None:
        claims["sid"] = session_family_id
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
