"""Phase 3H: confirms the new @limiter.limit(...) decorators on the
heavy Phase 2 read routes (/technical, /decision-v2, /opportunities)
actually fire -- these previously had no rate limit at all. Real
Redis-backed slowapi (not mocked), same pattern as
test_auth_rate_limiting.py: a decorator only proves itself by actually
exceeding the configured limit within the window.
"""

import pytest


def _redis_available() -> bool:
    try:
        import redis

        return redis.Redis(host="localhost", port=6379, socket_connect_timeout=1).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not available")


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    """These routes require require_active_subscription() -- see
    conftest.py's authenticated_as_staff."""


def _reset_bucket(route: str) -> None:
    import redis

    client = redis.Redis(host="localhost", port=6379)
    for key in client.keys(f"LIMITER/*{route}*"):
        client.delete(key)
    if not client.keys(f"LIMITER/*{route}*"):
        client.flushdb()


@pytest.fixture(autouse=True)
def _clean_shared_redis_bucket():
    """The Redis-backed limiter is process-wide and keyed by client IP
    (all TestClient requests share the "testclient" key) -- deliberately
    exhausting a bucket here must not leak into any other test file that
    happens to run afterward in the same pytest session, so reset both
    before AND after every test in this module."""
    yield
    import redis

    redis.Redis(host="localhost", port=6379).flushdb()


def test_technical_is_rate_limited_at_60_per_minute(client):
    _reset_bucket("technical")
    statuses = [client.get("/api/v1/stocks/9999/technical").status_code for _ in range(61)]
    assert 429 in statuses


def test_decision_v2_is_rate_limited_at_60_per_minute(client):
    _reset_bucket("decision-v2")
    statuses = [client.get("/api/v1/stocks/9999/decision-v2").status_code for _ in range(61)]
    assert 429 in statuses


def test_opportunities_is_rate_limited_at_30_per_minute(client):
    _reset_bucket("opportunities")
    statuses = [client.get("/api/v1/market/opportunities").status_code for _ in range(31)]
    assert 429 in statuses
