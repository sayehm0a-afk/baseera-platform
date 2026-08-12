"""M8 security acceptance pass: confirms the new @limiter.limit("30/minute")
decorator on POST /api/v1/portfolio/analyze actually fires -- this route
previously had no rate limit at all, unlike every other
computation-triggering customer route (see the module docstring in
src/api/routes/portfolio.py). Real Redis-backed slowapi (not mocked), same
pattern as test_stocks_and_market_rate_limiting.py: a decorator only proves
itself by actually exceeding the configured limit within the window.
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
    """POST /analyze requires require_active_subscription() -- see
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


def test_analyze_is_rate_limited_at_30_per_minute(client):
    _reset_bucket("analyze")
    statuses = [
        client.post("/api/v1/portfolio/analyze", json={"holdings": [], "cash": 0}).status_code for _ in range(31)
    ]
    assert 429 in statuses
