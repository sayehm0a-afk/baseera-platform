"""Integration tests for /api/v1/auth/* -- real FastAPI routing, real
Postgres-compatible SQLAlchemy models against in-memory SQLite (shared
conftest.py fixtures), real bcrypt/JWT/session-rotation logic. Only the
email transport is mocked (ConsoleEmailSender would only log -- these
tests need the actual raw token to drive verify/reset).

Rate limiting is disabled for this module: the login/register/
forgot-password limits are deliberately strict (5-10/minute) and would
make a test file that calls these routes repeatedly flaky under a
shared TestClient/IP key, so `limiter.enabled` is toggled off for the
duration of every test here -- rate-limit *behavior* itself is not
this file's concern.
"""

from typing import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.middleware.rate_limiting import limiter

pytest.importorskip("redis")


def _redis_available() -> bool:
    try:
        import redis

        return redis.Redis(host="localhost", port=6379, socket_connect_timeout=1).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not available")


@pytest.fixture(autouse=True)
def _disable_rate_limiting() -> Iterator[None]:
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _register_and_capture_verification_token(client: TestClient, email: str, password: str = "s3cret-password") -> str:
    with patch("src.auth.email_verification_service.get_email_sender") as mock_sender:
        response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
        assert response.status_code == 201, response.text
        raw_token = mock_sender.return_value.send_verification_email.call_args[0][1]
    return raw_token


def _csrf_headers(client: TestClient) -> dict:
    """Once a session cookie exists, CSRFMiddleware requires the
    non-httpOnly csrf_token cookie echoed back as this header on every
    non-GET /api/v1/* request -- see src/api/middleware/csrf.py."""
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}


def _register_verify_and_login(client: TestClient, email: str, password: str = "s3cret-password") -> None:
    raw_token = _register_and_capture_verification_token(client, email, password)
    verify_response = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verify_response.status_code == 200, verify_response.text

    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text


def test_register_returns_unverified_user(client: TestClient, db_session):
    response = client.post(
        "/api/v1/auth/register", json={"email": "new@example.com", "password": "s3cret-password"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["is_email_verified"] is False


def test_register_rejects_duplicate_email(client: TestClient, db_session):
    client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "s3cret-password"})
    response = client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "another-pass"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


def test_verify_email_with_invalid_token_returns_400(client: TestClient, db_session):
    response = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_or_expired_token"


def test_login_before_verification_is_rejected(client: TestClient, db_session):
    _register_and_capture_verification_token(client, "unverified@example.com")
    response = client.post(
        "/api/v1/auth/login", json={"email": "unverified@example.com", "password": "s3cret-password"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


def test_login_sets_session_cookies(client: TestClient, db_session):
    _register_verify_and_login(client, "cookies@example.com")
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies
    assert "csrf_token" in client.cookies


def test_login_with_wrong_password_returns_401(client: TestClient, db_session):
    _register_verify_and_login(client, "wrongpass@example.com")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "totally-wrong"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_requires_authentication(client: TestClient, db_session):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_returns_current_user_after_login(client: TestClient, db_session):
    _register_verify_and_login(client, "me@example.com")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_refresh_rotates_cookies_and_old_refresh_token_is_dead(client: TestClient, db_session):
    _register_verify_and_login(client, "refresh@example.com")
    old_refresh = client.cookies.get("refresh_token")

    refresh_response = client.post("/api/v1/auth/refresh", headers=_csrf_headers(client))
    assert refresh_response.status_code == 200
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh != old_refresh

    # Presenting the old (already-rotated) refresh token is rejected.
    client.cookies.set("refresh_token", old_refresh)
    replay_response = client.post("/api/v1/auth/refresh", headers=_csrf_headers(client))
    assert replay_response.status_code == 400
    assert replay_response.json()["error"]["code"] == "invalid_or_expired_token"


def test_logout_clears_session_and_revokes_it(client: TestClient, db_session):
    _register_verify_and_login(client, "logout@example.com")

    logout_response = client.post("/api/v1/auth/logout", headers=_csrf_headers(client))
    assert logout_response.status_code == 200

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_sessions_lists_current_device_as_current(client: TestClient, db_session):
    _register_verify_and_login(client, "sessions@example.com")
    response = client.get("/api/v1/auth/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True


def test_revoke_own_current_session_logs_it_out_immediately(client: TestClient, db_session):
    # Revoking the session tied to the cookie you're calling with is
    # indistinguishable from a normal logout, so it gets the same
    # instant access-token kill (not just a dead future refresh).
    _register_verify_and_login(client, "revoke@example.com")
    session_id = client.get("/api/v1/auth/sessions").json()[0]["id"]

    response = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=_csrf_headers(client))
    assert response.status_code == 200

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_revoke_a_different_devices_session_kills_its_refresh_not_its_live_access_token(
    client: TestClient, db_session
):
    # Access tokens are stateless JWTs, not checked against Redis on
    # the ordinary request path (see src/auth/token_store.py) -- there
    # is no way to instantly kill a *different* device's still-live
    # access token from here, only its ability to refresh going
    # forward. This is a deliberate, documented tradeoff, not a bug.
    _register_verify_and_login(client, "otherdevice@example.com")
    other_device_refresh_token = client.cookies.get("refresh_token")
    csrf_headers = _csrf_headers(client)  # csrf_token cookie is unaffected by the refresh_token deletion below
    session_id = client.get("/api/v1/auth/sessions").json()[0]["id"]

    # Simulate calling from a *different* device: no refresh_token
    # cookie matching the session being revoked is presented.
    client.cookies.delete("refresh_token")
    response = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=csrf_headers)
    assert response.status_code == 200

    # The current (still-live, unexpired) access token keeps working.
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200

    # But the revoked session's refresh token is dead.
    client.cookies.set("refresh_token", other_device_refresh_token)
    refresh_response = client.post("/api/v1/auth/refresh", headers=csrf_headers)
    assert refresh_response.status_code == 400


def test_revoke_unknown_session_returns_404(client: TestClient, db_session):
    _register_verify_and_login(client, "revoke404@example.com")
    response = client.delete("/api/v1/auth/sessions/999999", headers=_csrf_headers(client))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


def test_forgot_password_for_unknown_email_returns_generic_message(client: TestClient, db_session):
    response = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert "message" in response.json()


def test_forgot_password_and_reset_changes_password_and_revokes_sessions(client: TestClient, db_session):
    _register_verify_and_login(client, "reset@example.com", password="old-password")

    with patch("src.auth.password_reset_service.get_email_sender") as mock_sender:
        forgot_response = client.post(
            "/api/v1/auth/forgot-password", json={"email": "reset@example.com"}, headers=_csrf_headers(client)
        )
        assert forgot_response.status_code == 200
        raw_token = mock_sender.return_value.send_password_reset_email.call_args[0][1]

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password"},
        headers=_csrf_headers(client),
    )
    assert reset_response.status_code == 200

    # The session established before the reset must no longer work.
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401

    # New password works; old password no longer does.
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "old-password"},
        headers=_csrf_headers(client),
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "brand-new-password"},
        headers=_csrf_headers(client),
    )
    assert new_login.status_code == 200


def test_logout_all_revokes_every_session(client: TestClient, db_session):
    _register_verify_and_login(client, "logoutall@example.com")
    response = client.post("/api/v1/auth/logout-all", headers=_csrf_headers(client))
    assert response.status_code == 200

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_logout_all_kills_a_still_live_access_token_on_another_device_too(client: TestClient, db_session):
    # "Sign out everywhere" must reach a device that never sees this
    # response (so its cookies are never cleared) and whose access
    # token has not yet naturally expired -- that's exactly what
    # User.tokens_invalid_before exists for (see get_current_user).
    email = "multidevice@example.com"
    _register_verify_and_login(client, email)
    device_a_access_token = client.cookies.get("access_token")

    # A second login, simulating a second device -- overwrites this
    # client's cookies, but device A's captured token above is still
    # cryptographically valid and unexpired.
    client.post(
        "/api/v1/auth/login", json={"email": email, "password": "s3cret-password"}, headers=_csrf_headers(client)
    )

    logout_all_response = client.post("/api/v1/auth/logout-all", headers=_csrf_headers(client))
    assert logout_all_response.status_code == 200

    client.cookies.set("access_token", device_a_access_token)
    device_a_me_response = client.get("/api/v1/auth/me")
    assert device_a_me_response.status_code == 401
    assert device_a_me_response.json()["error"]["code"] == "unauthenticated"
