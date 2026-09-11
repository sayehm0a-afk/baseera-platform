"""PR #114 follow-up, twice over.

Round 1 proved `auth_target_key` (src/api/middleware/rate_limiting.py)
fixes the "everyone shares the frontend's address" problem: once the
frontend proxies every browser request through its own Next.js server
(see docs/governance/ADR-safari-session-recovery.md), `request.client.
host` becomes the frontend's own address for every visitor, and keying
purely on that would collapse every distinct user's login/register/
refresh budget into one shared bucket.

Round 2 (this file, after a security review) closes the gap that fix
introduced: `auth_target_key` alone lets an attacker refill its own
budget for free by presenting a different email or token on every
request -- nothing validates that identity against a real record
before the rate-limit check runs, so a never-used email or a freshly
invented token/refresh-token-cookie value always lands in a bucket
nobody has touched yet. `enforce_network_ceiling` restores the
account/token check's ORIGINAL, unspoofable `get_remote_address`-keyed
ceiling as a SECOND, independent, both-must-pass gate at the exact same
configured threshold -- never merged into one key, never a raised
limit, and never `X-Forwarded-For` (trivially attacker-suppliable,
never read anywhere in this codebase's rate limiting).

Real Redis-backed slowapi (not mocked), same pattern as
test_auth_rate_limiting.py: a rate limit only proves itself by actually
being hit. Tests that need two genuinely INDEPENDENT network sources
(to isolate the per-account layer from the per-network layer) construct
a second `TestClient(main.app, client=(ip, port))` -- Starlette's
TestClient accepts a `client` tuple that becomes `request.client.host`
for every request made through that instance, letting a test simulate
two different real visitors without touching any header.
"""

import secrets

import pytest
from starlette.testclient import TestClient

import main

from src.api.middleware.rate_limiting import auth_target_key


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


def _client_from(address: str, port: int = 12345) -> TestClient:
    """A second TestClient simulating a genuinely different real
    visitor -- same app/dependency_overrides (set on main.app itself
    by the `client`/`db_session` fixtures a test also depends on), a
    different `request.client.host`."""
    return TestClient(main.app, client=(address, port))


# --- Round 1: per-account/token isolation still holds -----------------------


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


def test_different_accounts_from_different_network_addresses_get_independent_login_buckets(db_session):
    """Two different real visitors (two different network addresses),
    each targeting a different account: each must be able to exhaust
    its OWN account's budget on its OWN address without affecting the
    other -- proving `auth_target_key`'s per-account isolation still
    holds once genuinely different sources are involved, independent of
    `enforce_network_ceiling`'s separate per-address gate."""
    client_a = _client_from("203.0.113.10")
    client_b = _client_from("203.0.113.20")

    victim_a_statuses = [
        client_a.post(
            "/api/v1/auth/login", json={"email": "victim-a@example.com", "password": "wrong-password"}
        ).status_code
        for _ in range(11)
    ]
    assert 429 in victim_a_statuses, "victim-a's own budget should have been exhausted by the 11th attempt"

    # A different account, from a different address, must not see any
    # effect from victim-a's exhausted budget on a different address.
    victim_b_response = client_b.post(
        "/api/v1/auth/login", json={"email": "victim-b@example.com", "password": "wrong-password"}
    )
    assert victim_b_response.status_code != 429


def test_forged_x_forwarded_for_does_not_change_or_bypass_the_limit(client):
    """A spoofed X-Forwarded-For claiming a different "client" on every
    request must have zero effect: neither auth_target_key nor
    enforce_network_ceiling ever reads that header, so the budget must
    exhaust at exactly the same 11th attempt as the unspoofed baseline
    test above."""
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


# --- Round 2: identity-cycling can no longer refill the budget for free -----


def test_varying_email_on_register_no_longer_bypasses_the_shared_network_ceiling(client):
    """The exact gap this round closes: before enforce_network_ceiling
    existed, an attacker hitting /register with a BRAND NEW, never-
    used email on every single request paid nothing -- auth_target_key
    gave each one its own untouched bucket. enforce_network_ceiling
    restores the original address-keyed ceiling (5/minute, same value
    /register already had) as a second gate that identity-cycling
    cannot refill, because it never looks at the identity at all."""
    statuses = [
        client.post(
            "/api/v1/auth/register",
            json={
                "email": f"never-used-{secrets.token_hex(8)}@example.com",
                "password": "correct-horse-1",
                "full_name": "T",
            },
        ).status_code
        for _ in range(6)
    ]
    # Exact position, not just "429 shows up somewhere": the first 5
    # (each a genuinely distinct, previously-unregistered account) must
    # succeed on their own account-level merits, and only the 6th --
    # exceeding the network ceiling's own 5/minute budget -- must be
    # blocked. A weaker "429 in statuses" check would also pass for an
    # accidentally-too-strict ceiling that blocks far earlier than
    # intended, silently hiding that regression.
    assert statuses == [201, 201, 201, 201, 201, 429], (
        f"expected the first 5 (distinct accounts) to succeed and only the 6th to be network-ceiling-blocked, "
        f"got {statuses}"
    )


def test_varying_invalid_token_on_verify_email_no_longer_bypasses_the_shared_network_ceiling(client):
    """Same gap, worse on a token-keyed route: nothing validates a
    presented verify-email token against a real record before the rate
    limit runs, so a freshly made-up token used to always land in an
    untouched bucket. enforce_network_ceiling closes it the same way,
    at /verify-email's existing 10/minute value."""
    statuses = [
        client.post(
            "/api/v1/auth/verify-email", json={"token": f"never-seen-token-{secrets.token_hex(16)}"}
        ).status_code
        for _ in range(11)
    ]
    # Exact position: each fake token is rejected as invalid (400,
    # InvalidOrExpiredTokenError) on its own account-level merits for
    # the first 10, and only the 11th -- exceeding the network
    # ceiling's 10/minute budget -- must be blocked with 429.
    assert statuses == [400] * 10 + [429], (
        f"expected the first 10 fake-token attempts to be rejected as invalid (400) and only the "
        f"11th to be network-ceiling-blocked (429), got {statuses}"
    )


def test_varying_fake_refresh_cookie_no_longer_bypasses_the_shared_network_ceiling(client):
    """Same gap on /refresh: a different, entirely invented
    refresh_token cookie value on every request used to always hash to
    an untouched bucket. enforce_network_ceiling closes it at
    /refresh's existing 30/minute value."""
    client.cookies.set("csrf_token", "test-csrf-token")
    statuses = []
    for _ in range(31):
        client.cookies.set("refresh_token", f"never-seen-refresh-{secrets.token_hex(16)}")
        statuses.append(
            client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "test-csrf-token"}).status_code
        )
    # Exact position: each fake refresh_token is rejected as unknown
    # (400, InvalidOrExpiredTokenError) for the first 30, and only the
    # 31st -- exceeding the network ceiling's 30/minute budget -- must
    # be blocked with 429.
    assert statuses == [400] * 30 + [429], (
        f"expected the first 30 fake-cookie attempts to be rejected as invalid (400) and only the "
        f"31st to be network-ceiling-blocked (429), got {statuses}"
    )


def test_network_ceiling_does_not_block_reasonable_traffic_from_two_real_sources(client):
    """Sanity/regression check the size of the fix: enforce_network_ceiling
    must not be so aggressive that ordinary, well-under-threshold traffic
    from two genuinely different sources ever spuriously collides."""
    client_a = _client_from("198.51.100.1")
    client_b = _client_from("198.51.100.2")

    for _ in range(3):
        assert (
            client_a.post(
                "/api/v1/auth/login", json={"email": "legit-a@example.com", "password": "wrong-password"}
            ).status_code
            != 429
        )
    for _ in range(3):
        assert (
            client_b.post(
                "/api/v1/auth/login", json={"email": "legit-b@example.com", "password": "wrong-password"}
            ).status_code
            != 429
        )


def test_network_ceiling_429_has_the_same_response_envelope_as_auth_target_key_429(client):
    """A request blocked by `enforce_network_ceiling` must return the
    exact same JSON error envelope as one blocked by `auth_target_key`
    -- both flow through the same `RateLimitExceeded` handler in
    main.py. This specifically guards `enforce_network_ceiling`'s own
    `request.state.view_rate_limit = None` line: without it, that
    handler's unconditional read of `request.state.view_rate_limit`
    raises `AttributeError` (FastAPI resolves this dependency before
    `auth_target_key`'s own decorator ever runs and sets that
    attribute), turning an intended 429 into an unhandled 500 --
    exactly the kind of regression a future "cleanup" of that
    seemingly-redundant line could silently reintroduce, and a bare
    `status_code == 429` assertion elsewhere in this file would not
    catch."""
    # Exhaust the network ceiling via identity-cycling on /register --
    # each request has a brand-new email, so auth_target_key's own
    # per-account check never fires; only enforce_network_ceiling can
    # be responsible for the 6th request's block.
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": f"envelope-check-{secrets.token_hex(8)}@example.com", "password": "correct-horse-1"},
        )
        assert response.status_code == 201

    blocked = client.post(
        "/api/v1/auth/register",
        json={"email": f"envelope-check-{secrets.token_hex(8)}@example.com", "password": "correct-horse-1"},
    )
    assert blocked.status_code == 429
    body = blocked.json()
    assert "error" in body and "Rate limit exceeded" in body["error"], (
        f"expected the same {{'error': 'Rate limit exceeded: ...'}} envelope auth_target_key's own "
        f"429s use, got {body}"
    )


# --- Email normalization must match the real authentication logic ----------


def test_auth_target_key_normalizes_email_exactly_like_user_service():
    """`auth_target_key` computes its own `email.strip().lower()` --
    this must match user_service.register()/authenticate()'s own
    normalization exactly (see src/auth/user_service.py), or the rate
    limiter could either fail to merge two requests for the SAME real
    account (a differently-cased or padded variant slips into its own
    fresh bucket -- reopening the identity-cycling gap for free, via
    nothing more than "MailTo@Example.com " vs "mailto@example.com"),
    or wrongly merge two DIFFERENT accounts that only coincidentally
    differ by case/whitespace before normalization."""
    import json
    from types import SimpleNamespace

    variants = [
        "Victim@Example.com",
        "victim@example.com",
        "  victim@example.com  ",
        "VICTIM@EXAMPLE.COM",
        "\tvictim@example.com\n",
    ]

    def _key_for(raw_email: str) -> str:
        body_bytes = json.dumps({"email": raw_email}).encode("utf-8")
        fake_request = SimpleNamespace(_body=body_bytes, cookies={})
        return auth_target_key(fake_request)

    keys = {_key_for(v) for v in variants}
    assert len(keys) == 1, f"differently-cased/padded variants of the same email produced different keys: {keys}"

    # And that single shared key must equal exactly what user_service's
    # own authenticate()/register() would normalize the same input to.
    (only_key,) = keys
    assert only_key == f"acct:{'victim@example.com'.strip().lower()}"
    for v in variants:
        assert only_key == f"acct:{v.strip().lower()}"
