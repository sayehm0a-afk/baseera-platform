"""Unit tests for `auth_target_key` (src/api/middleware/rate_limiting.py)
-- pure function behavior, no Redis/network required (contrast with
tests/integration/api/test_auth_rate_limiting_identity_isolation.py,
which proves the same function's effect through real rate-limit hits).

2026-09-19 (full-platform audit): covers the `mfa_token` branch added
to fix a real gap -- `POST /auth/mfa/login-verify`'s body field is
named `mfa_token` (see MfaLoginVerifyRequest), not `token`, so before
this fix every request to that route fell through to the `net:`
fallback, silently collapsing its per-account TOTP/backup-code
brute-force limit into the same IP-wide bucket `enforce_network_
ceiling` already covers independently.
"""

import json

from starlette.requests import Request

from src.api.middleware.rate_limiting import auth_target_key
from src.auth.token_hashing import hash_token


def _make_request(body: dict | None = None, cookies: dict | None = None) -> Request:
    headers = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))
    request = Request({"type": "http", "headers": headers})
    # `_already_parsed_json_body` reads the same cached `_body` attribute
    # Starlette's own `Request.body()` sets after FastAPI's dependency
    # resolution has already parsed the route's Pydantic body -- set
    # directly here since this unit test never runs through the app.
    request._body = json.dumps(body).encode() if body is not None else b""
    return request


def test_keys_on_email_when_present():
    request = _make_request(body={"email": "User@Example.com"})
    assert auth_target_key(request) == "acct:user@example.com"


def test_keys_on_token_when_present():
    request = _make_request(body={"token": "abc123"})
    assert auth_target_key(request) == f"tok:{hash_token('abc123')}"


def test_keys_on_mfa_token_when_present():
    """The gap this fix closes: MfaLoginVerifyRequest's field is
    `mfa_token`, not `token` -- must resolve to its own real per-token
    bucket, never the `net:` fallback."""
    request = _make_request(body={"mfa_token": "pending-xyz", "code": "123456"})
    assert auth_target_key(request) == f"tok:{hash_token('pending-xyz')}"


def test_email_takes_priority_over_mfa_token_when_both_present():
    request = _make_request(body={"email": "a@example.com", "mfa_token": "xyz"})
    assert auth_target_key(request) == "acct:a@example.com"


def test_token_takes_priority_over_mfa_token_when_both_present():
    request = _make_request(body={"token": "tkn", "mfa_token": "xyz"})
    assert auth_target_key(request) == f"tok:{hash_token('tkn')}"


def test_keys_on_refresh_cookie_when_no_body_identity_present():
    request = _make_request(cookies={"refresh_token": "rt-value"})
    assert auth_target_key(request) == f"tok:{hash_token('rt-value')}"


def test_falls_back_to_network_address_when_no_identity_present():
    request = _make_request()
    assert auth_target_key(request).startswith("net:")


def test_ignores_a_blank_mfa_token():
    request = _make_request(body={"mfa_token": ""})
    assert auth_target_key(request).startswith("net:")
