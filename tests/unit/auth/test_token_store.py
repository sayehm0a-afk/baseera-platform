"""Tests against a real Redis instance -- skipped (not mocked) when
Redis isn't reachable, the same convention
tests/integration/test_production_integration.py already establishes
for this codebase's other Redis-touching code.
"""

import uuid

import pytest


def is_redis_available() -> bool:
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not is_redis_available(), reason="Redis not available")


@pytest.fixture(autouse=True)
def _clean_up_test_keys():
    from src.auth.token_store import get_redis_client

    yield
    client = get_redis_client()
    for pattern in ("authsession:test-*", "auth:revoked-access-jti:test-*"):
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)


def _jti() -> str:
    return f"test-{uuid.uuid4().hex}"


def test_store_and_get_refresh_session():
    from src.auth.token_store import get_refresh_session_user_id, store_refresh_session

    jti = _jti()
    store_refresh_session(jti, user_id=42, ttl_seconds=60)
    assert get_refresh_session_user_id(jti) == 42


def test_get_unknown_refresh_session_returns_none():
    from src.auth.token_store import get_refresh_session_user_id

    assert get_refresh_session_user_id(_jti()) is None


def test_delete_refresh_session():
    from src.auth.token_store import delete_refresh_session, get_refresh_session_user_id, store_refresh_session

    jti = _jti()
    store_refresh_session(jti, user_id=1, ttl_seconds=60)
    delete_refresh_session(jti)
    assert get_refresh_session_user_id(jti) is None


def test_revoke_and_check_access_token():
    from src.auth.token_store import is_access_token_revoked, revoke_access_token

    jti = _jti()
    assert is_access_token_revoked(jti) is False
    revoke_access_token(jti, ttl_seconds=60)
    assert is_access_token_revoked(jti) is True


def test_revoke_access_token_with_zero_ttl_is_a_no_op():
    from src.auth.token_store import is_access_token_revoked, revoke_access_token

    jti = _jti()
    revoke_access_token(jti, ttl_seconds=0)
    assert is_access_token_revoked(jti) is False
