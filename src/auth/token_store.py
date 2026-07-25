"""Redis-backed refresh-token allowlist + short-lived access-token
revocation set.

Refresh tokens are opaque (not JWTs) precisely so they can be revoked by
a simple key lookup/delete -- the `authsession:{jti}` key existing in
Redis (with a TTL matching the token's own lifetime) IS the "is this
refresh token currently valid" check. This is an allowlist, not a
blacklist: it self-expires (no unbounded growth) and a Redis flush
degrades safely to "every session needs to re-authenticate," never to
"a revoked session becomes valid again" -- `UserSession.revoked_at` in
Postgres (src/domain/models/user_session.py) is still checked by
anything reading the durable record (e.g. session listing), so Redis is
a fast-path cache of that table's state, not an independent source of
truth for revocation itself.

Access tokens are stateless JWTs (src/auth/jwt_service.py) and are NOT
checked against Redis on the ordinary request path -- only the two
explicit-revocation cases below (logout of a still-live token, or an
admin/support action) populate `auth:revoked-access-jti:{jti}`, and only
those specific code paths need to check it.
"""

from typing import Optional

import redis

from src.core.config import settings

_REFRESH_SESSION_KEY_PREFIX = "authsession"
_REVOKED_ACCESS_JTI_KEY_PREFIX = "auth:revoked-access-jti"

_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
        )
    return _client


def _refresh_session_key(jti: str) -> str:
    return f"{_REFRESH_SESSION_KEY_PREFIX}:{jti}"


def _revoked_access_jti_key(jti: str) -> str:
    return f"{_REVOKED_ACCESS_JTI_KEY_PREFIX}:{jti}"


def store_refresh_session(jti: str, user_id: int, ttl_seconds: int) -> None:
    get_redis_client().setex(_refresh_session_key(jti), ttl_seconds, str(user_id))


def get_refresh_session_user_id(jti: str) -> Optional[int]:
    value = get_redis_client().get(_refresh_session_key(jti))
    return int(value) if value is not None else None


def delete_refresh_session(jti: str) -> None:
    get_redis_client().delete(_refresh_session_key(jti))


def revoke_access_token(jti: str, ttl_seconds: int) -> None:
    """Only called for explicit revocation of a still-live access token
    (logout, admin suspend) -- never on the ordinary request path."""
    if ttl_seconds <= 0:
        return
    get_redis_client().setex(_revoked_access_jti_key(jti), ttl_seconds, "1")


def is_access_token_revoked(jti: str) -> bool:
    return get_redis_client().exists(_revoked_access_jti_key(jti)) > 0
