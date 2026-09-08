"""PR #114 follow-up: proves `auth_target_key` (src/api/middleware/
rate_limiting.py) actually fixes the problem it exists to fix, now that
the frontend proxies every browser request through its own Next.js
server (see docs/governance/ADR-safari-session-recovery.md) instead of
calling the backend cross-origin.

Before that change, `get_remote_address()` -- keyed on
`request.client.host` -- already gave every real visitor an
independent rate-limit bucket, because each browser connected to the
backend directly. Once the frontend proxies `/api/v1/*` server-to-
server, every browser request would instead arrive from the *same*
address (the frontend container's own), collapsing every distinct
user's login/register/refresh budget into one shared bucket unless the
key changes to something a network hop cannot affect.

Same pattern as test_auth_rate_limiting.py: real Redis-backed slowapi
(not mocked) -- a rate limit only proves itself by actually being hit.
A single shared TestClient inherently gives every request in this file
the same `request.client.host` ("testclient"), which is exactly the
"everyone shares the frontend's address" scenario this fix targets --
so any isolation seen here across different emails is proof the fix
works, not an artifact of the test setup.
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
def _flush_rate_limit_state():
    import redis

    r = redis.Redis(host="localhost", port=6379)
    r.flushdb()
    yield
    r.flushdb()


def test_register_is_still_rate_limited_at_5_per_minute(client):
    statuses = [
        client.post(
            "/api/v1/auth/register",
            json={"email": "brute-target@example.com", "password": "correct-horse-1", "full_name": "T"},
        ).status_code
        for _ in range(6)
    ]
    assert 429 in statuses


def test_login_is_still_rate_limited_at_10_per_minute(client):
    statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": "brute-target@example.com", "password": "wrong-password"}
        ).status_code
        for _ in range(11)
    ]
    assert 429 in statuses


def test_refresh_is_still_rate_limited_at_30_per_minute_keyed_by_cookie(client):
    # No real login needed -- the identity key is derived from whatever
    # refresh_token cookie is presented, valid or not; the route itself
    # rejects an invalid one with 401 well after slowapi's check runs.
    # A refresh_token cookie makes CSRFMiddleware (src/api/middleware/
    # csrf.py) require a matching double-submit token before the
    # request reaches routing at all, so both must be set too.
    client.cookies.set("refresh_token", "not-a-real-refresh-token")
    client.cookies.set("csrf_token", "test-csrf-token")
    statuses = [
        client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "test-csrf-token"}).status_code
        for _ in range(31)
    ]
    assert 429 in statuses


def test_different_accounts_get_independent_login_buckets_despite_shared_client_address(client):
    """The core proxy-pooling fix: two different targeted accounts must
    not share one budget merely because every request in this process
    (like every real browser request once proxied through the
    frontend) reports the same `request.client.host`."""
    victim_a_statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": "victim-a@example.com", "password": "wrong-password"}
        ).status_code
        for _ in range(11)
    ]
    assert 429 in victim_a_statuses, "victim-a's own budget should have been exhausted by the 11th attempt"

    # A completely different account's very first attempt, made
    # immediately afterward from the exact same TestClient (same
    # simulated network address), must NOT be blocked by victim-a's
    # exhausted budget.
    victim_b_response = client.post(
        "/api/v1/auth/login", json={"email": "victim-b@example.com", "password": "wrong-password"}
    )
    assert victim_b_response.status_code != 429


def test_forged_x_forwarded_for_does_not_change_or_bypass_the_limit(client):
    """A spoofed X-Forwarded-For claiming a different "client" on every
    request must have zero effect: auth_target_key never reads that
    header at all, so the account-targeted budget must exhaust at
    exactly the same 11th attempt as the unspoofed baseline test above."""
    statuses = []
    for i in range(11):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "spoof-target@example.com", "password": "wrong-password"},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
        )
        statuses.append(response.status_code)
    assert 429 in statuses
    assert statuses.index(429) == 10, (
        "a forged, ever-changing X-Forwarded-For let more than 10 attempts through "
        "before the limit fired -- the header is influencing the rate-limit key"
    )


def test_forged_x_forwarded_for_cannot_reset_an_already_exhausted_bucket(client):
    """Exhaust the real budget for one account with a plain client (no
    X-Forwarded-For at all), then confirm a forged header on the very
    next attempt for the SAME account still gets rejected -- proving
    the header cannot be used to obtain a "fresh" bucket for an
    account whose budget is already spent."""
    for _ in range(10):
        client.post(
            "/api/v1/auth/login", json={"email": "reset-attempt@example.com", "password": "wrong-password"}
        )

    spoofed_response = client.post(
        "/api/v1/auth/login",
        json={"email": "reset-attempt@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "198.51.100.77"},
    )
    assert spoofed_response.status_code == 429
