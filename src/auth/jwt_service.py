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
