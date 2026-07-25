"""Integration tests for the security middleware stack wired into
main.py -- SecurityHeadersMiddleware and CSRFMiddleware. Uses the real
`main.app` directly (no DB fixture needed): CSRF rejections happen in
the ASGI middleware layer, before any route/dependency runs, so these
tests never need a database.
"""

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def _is_csrf_failure(response) -> bool:
    return response.status_code == 403 and response.json().get("error", {}).get("code") == "csrf_verification_failed"


# --- security headers ----------------------------------------------------


def test_security_headers_present_on_every_response(client):
    response = client.get("/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_hsts_absent_outside_production(client):
    # settings.environment defaults to "development" whenever
    # BASEERA_ENV is unset, which is how the whole test suite runs.
    response = client.get("/health/live")
    assert "Strict-Transport-Security" not in response.headers


# --- CSRF ------------------------------------------------------------------


def test_get_requests_never_require_a_csrf_token(client):
    client.cookies.set("access_token", "whatever")
    response = client.get("/health/live")
    assert response.status_code == 200


def test_mutating_request_with_no_session_cookie_is_not_csrf_blocked(client):
    # No access_token/refresh_token cookie at all -- CSRFMiddleware has
    # nothing to protect, so this must reach the actual route (which
    # will reject it for its own, unrelated reasons -- missing fields
    # -- never for a CSRF failure).
    response = client.post("/api/v1/auth/register", json={})
    assert not _is_csrf_failure(response)


def test_mutating_request_with_a_session_cookie_but_no_csrf_header_is_blocked(client):
    client.cookies.set("access_token", "whatever")
    client.cookies.set("csrf_token", "the-real-token")
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_verification_failed"


def test_mutating_request_with_a_mismatched_csrf_header_is_blocked(client):
    client.cookies.set("access_token", "whatever")
    client.cookies.set("csrf_token", "the-real-token")
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "a-different-token"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_verification_failed"


def test_mutating_request_with_a_matching_csrf_header_passes_the_csrf_check(client):
    client.cookies.set("access_token", "whatever")
    client.cookies.set("csrf_token", "the-real-token")
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "the-real-token"})
    # Reaches the real route logic -- not blocked by CSRF.
    assert not _is_csrf_failure(response)


def test_non_api_v1_paths_are_never_csrf_checked(client):
    client.cookies.set("access_token", "whatever")
    response = client.post(
        "/api/tasks", json={"task_id": "t1", "agent_id": "a1", "task_type": "test", "data": {}}
    )
    assert not _is_csrf_failure(response)
