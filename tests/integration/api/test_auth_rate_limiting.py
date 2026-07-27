"""Integration tests confirming the Phase 13 P13.3 rate-limit additions
on /auth/verify-email, /auth/refresh, /auth/reset-password actually
fire -- these three had no @limiter.limit(...) decorator before this
milestone. Real Redis-backed slowapi (not mocked): rate-limit state is
per-key (client IP) storage in Redis, so the decorator only proves
itself by actually exceeding the configured limit within the window.

Uses the shared `client`/`db_session` fixtures from
tests/integration/api/conftest.py (in-memory SQLite via
main.app.dependency_overrides) -- the exact same pattern every other
file in this directory already uses.
"""

import pytest


def _redis_available() -> bool:
    try:
        import redis

        return redis.Redis(host="localhost", port=6379, socket_connect_timeout=1).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not available")


def _reset_bucket(route: str) -> None:
    """slowapi's Redis keys are per-(route, key_func) -- flush any state
    a previous test in this same Redis instance may have left, so each
    test starts from a clean budget regardless of run order."""
    import redis

    client = redis.Redis(host="localhost", port=6379)
    for key in client.keys(f"LIMITER/*{route}*"):
        client.delete(key)
    # slowapi's default key pattern is opaque enough that a broad flush
    # is simpler and safer than reverse-engineering it; fall back to a
    # full flush of the test DB if nothing matched.
    if not client.keys(f"LIMITER/*{route}*"):
        client.flushdb()


def test_verify_email_is_rate_limited_at_10_per_minute(client):
    _reset_bucket("verify-email")
    statuses = [
        client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"}).status_code
        for _ in range(11)
    ]
    assert 429 in statuses


def test_refresh_is_rate_limited_at_30_per_minute(client):
    _reset_bucket("refresh")
    statuses = [client.post("/api/v1/auth/refresh").status_code for _ in range(31)]
    assert 429 in statuses


def test_reset_password_is_rate_limited_at_5_per_minute(client):
    _reset_bucket("reset-password")
    statuses = [
        client.post(
            "/api/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "irrelevant-123"}
        ).status_code
        for _ in range(6)
    ]
    assert 429 in statuses
