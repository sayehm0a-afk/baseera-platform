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
from src.domain.models import User

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


def _set_cookie_attrs(set_cookie_headers: list, cookie_name: str) -> str:
    """Pulls the one Set-Cookie line for `cookie_name` out of a response's
    (possibly several) Set-Cookie headers -- TestClient/httpx exposes
    them via response.headers.get_list("set-cookie"), same as a real
    HTTP response can carry more than one Set-Cookie line."""
    matches = [h for h in set_cookie_headers if h.startswith(f"{cookie_name}=")]
    assert matches, f"No Set-Cookie header found for {cookie_name!r} in {set_cookie_headers!r}"
    return matches[0]


def test_login_cookies_are_samesite_lax_and_not_secure_outside_production(client: TestClient, db_session):
    """Locally / in CI (settings.is_production is False, the default),
    frontend and backend are same-site, so SameSite=Lax is correct and
    Secure is not required -- forcing Secure here would silently drop
    the cookie over a plain http:// dev server."""
    response = _login_and_capture_response(client, "lax@example.com")
    set_cookie = response.headers.get_list("set-cookie")

    access = _set_cookie_attrs(set_cookie, "access_token")
    assert "samesite=lax" in access.lower()
    assert "secure" not in access.lower()
    assert "httponly" in access.lower()

    refresh = _set_cookie_attrs(set_cookie, "refresh_token")
    assert "samesite=lax" in refresh.lower()
    assert "secure" not in refresh.lower()
    assert "httponly" in refresh.lower()

    csrf = _set_cookie_attrs(set_cookie, "csrf_token")
    assert "samesite=lax" in csrf.lower()
    assert "secure" not in csrf.lower()
    assert "httponly" not in csrf.lower()  # must stay JS-readable for same-origin setups


def test_login_cookies_are_samesite_none_and_secure_in_production(client: TestClient, db_session, monkeypatch):
    """Production (Railway): frontend and backend are different sites
    under up.railway.app (a registered Public Suffix List entry) --
    SameSite=None is required for the browser to ever send these
    cookies back on the frontend's cross-site fetch() calls, which
    every modern browser only allows when Secure is also set."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    response = _login_and_capture_response(client, "none-secure@example.com")
    set_cookie = response.headers.get_list("set-cookie")

    for name, expect_httponly in (
        ("access_token", True),
        ("refresh_token", True),
        ("csrf_token", False),
    ):
        cookie = _set_cookie_attrs(set_cookie, name)
        assert "samesite=none" in cookie.lower(), cookie
        assert "secure" in cookie.lower(), cookie
        assert ("httponly" in cookie.lower()) is expect_httponly, cookie


def test_login_echoes_csrf_token_as_a_response_header(client: TestClient, db_session):
    """The frontend runs on a different origin than this API and can't
    read the csrf_token cookie via document.cookie -- login (and
    refresh/me) echo the same value back as X-CSRF-Token so the
    frontend's JS can capture it directly from the response instead."""
    response = _login_and_capture_response(client, "csrfheader@example.com")
    header_value = response.headers.get("x-csrf-token")
    assert header_value
    assert header_value == client.cookies.get("csrf_token")


def test_me_echoes_csrf_token_as_a_response_header(client: TestClient, db_session):
    """Covers the reload case: the frontend's in-memory copy of the
    CSRF token (captured from a prior response header) is lost on a
    page reload, so /auth/me re-surfaces the existing cookie's value
    the same way, without rotating it."""
    _register_verify_and_login(client, "me-csrf@example.com")
    cookie_value = client.cookies.get("csrf_token")

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.headers.get("x-csrf-token") == cookie_value


def _login_and_capture_response(client: TestClient, email: str, password: str = "s3cret-password"):
    raw_token = _register_and_capture_verification_token(client, email, password)
    verify_response = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verify_response.status_code == 200, verify_response.text

    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    return login_response


def test_login_with_wrong_password_returns_401(client: TestClient, db_session):
    _register_verify_and_login(client, "wrongpass@example.com")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "totally-wrong"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_repeated_wrong_passwords_lock_the_account_via_the_login_route(client: TestClient, db_session, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "login_lockout_max_attempts", 3)
    _register_verify_and_login(client, "route-lockout@example.com")

    for _ in range(3):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "route-lockout@example.com", "password": "totally-wrong"},
            headers=_csrf_headers(client),
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/v1/auth/login",
        json={"email": "route-lockout@example.com", "password": "s3cret-password"},
        headers=_csrf_headers(client),
    )
    assert locked_response.status_code == 429
    assert locked_response.json()["error"]["code"] == "account_locked"


def test_me_requires_authentication(client: TestClient, db_session):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_returns_current_user_after_login(client: TestClient, db_session):
    _register_verify_and_login(client, "me@example.com")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_delete_own_account_requires_the_correct_password(client: TestClient, db_session):
    _register_verify_and_login(client, "deleteme@example.com")
    response = client.request(
        "DELETE",
        "/api/v1/auth/me",
        json={"password": "totally-wrong"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"

    # The account is still there and the caller is still logged in.
    assert client.get("/api/v1/auth/me").status_code == 200


def test_delete_own_account_removes_the_account_and_clears_cookies(client: TestClient, db_session):
    _register_verify_and_login(client, "deleteme@example.com")
    response = client.request(
        "DELETE",
        "/api/v1/auth/me",
        json={"password": "s3cret-password"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200
    assert "access_token" not in client.cookies

    # A deleted account can no longer log in.
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "deleteme@example.com", "password": "s3cret-password"}
    )
    assert login_response.status_code == 401


def test_deleting_an_already_deleted_account_is_a_clean_401_not_a_500(client: TestClient, db_session):
    """Idempotency: the second DELETE call reuses the exact same
    (now-stale) access-token cookie -- get_current_user's own user-
    lookup-by-id fails cleanly (401 unauthenticated) the moment the row
    is gone, so a retried/duplicated delete request can never 500 or
    silently "succeed" a second time against nothing."""
    _register_verify_and_login(client, "deletetwice@example.com")
    csrf_headers = _csrf_headers(client)

    first = client.request(
        "DELETE", "/api/v1/auth/me", json={"password": "s3cret-password"}, headers=csrf_headers
    )
    assert first.status_code == 200

    second = client.request(
        "DELETE", "/api/v1/auth/me", json={"password": "s3cret-password"}, headers=csrf_headers
    )
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "unauthenticated"


def test_delete_own_account_can_never_target_another_user(client: TestClient, db_session):
    """DeleteAccountRequest has no user-id/target field at all -- the
    route only ever operates on get_current_user's own resolved
    identity. Proven concretely: deleting "self" while logged in as
    user A never removes user B."""
    from src.auth.password_hashing import hash_password

    victim = User(email="untouched@example.com", password_hash=hash_password("victim-password"))
    db_session.add(victim)
    db_session.commit()
    victim_id = victim.id

    _register_verify_and_login(client, "selfdeleter@example.com")
    response = client.request(
        "DELETE", "/api/v1/auth/me", json={"password": "s3cret-password"}, headers=_csrf_headers(client)
    )
    assert response.status_code == 200

    assert db_session.query(User).filter_by(id=victim_id).one_or_none() is not None


def test_delete_own_account_ignores_an_injected_target_user_id_in_the_request_body(client: TestClient, db_session):
    """Belt-and-suspenders on top of the previous test: even if a
    caller tries to smuggle a target identifier into the request body,
    DeleteAccountRequest only ever declares `password`, so it's
    silently ignored -- the deletion still only ever affects the
    caller's own account (proven by the login-now-fails assertion)."""
    _register_verify_and_login(client, "injecttarget@example.com")
    response = client.request(
        "DELETE",
        "/api/v1/auth/me",
        json={"password": "s3cret-password", "user_id": 999999, "target_user_id": 1},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login", json={"email": "injecttarget@example.com", "password": "s3cret-password"}
    )
    assert login_response.status_code == 401


def test_export_own_data_requires_authentication(client: TestClient, db_session):
    response = client.get("/api/v1/auth/me/export")
    assert response.status_code == 401


def test_export_own_data_returns_the_callers_profile(client: TestClient, db_session):
    _register_verify_and_login(client, "exportme@example.com")
    response = client.get("/api/v1/auth/me/export")
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["email"] == "exportme@example.com"
    assert "password_hash" not in body["profile"]
    assert body["subscription"]["plan"] == "TRIAL"  # provisioned automatically on register


def test_export_own_data_never_leaks_another_users_email(client: TestClient, db_session):
    from src.auth.password_hashing import hash_password

    db_session.add(User(email="victim@example.com", password_hash=hash_password("whatever-password")))
    db_session.commit()

    _register_verify_and_login(client, "exporter@example.com")

    response = client.get("/api/v1/auth/me/export")
    assert response.status_code == 200
    assert "victim@example.com" not in response.text


def test_delete_own_account_blocks_a_staff_account(client: TestClient, db_session):
    from src.domain.models import StaffRole

    _register_verify_and_login(client, "staffowner@example.com")
    staff_user = db_session.query(User).filter_by(email="staffowner@example.com").one()
    staff_user.is_staff = True
    staff_user.staff_role = StaffRole.OWNER
    db_session.commit()

    # get_current_user re-reads the User row fresh from the DB on every
    # request, so the already-issued session cookie from the login
    # above picks up the is_staff promotion above with no override
    # needed -- exactly like a real staff-role grant would take effect
    # on a customer's very next request.
    response = client.request(
        "DELETE", "/api/v1/auth/me", json={"password": "s3cret-password"}, headers=_csrf_headers(client)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "staff_account_self_deletion_blocked"
    assert db_session.query(User).filter_by(email="staffowner@example.com").one_or_none() is not None


def test_delete_own_account_requires_authentication(client: TestClient, db_session):
    response = client.request("DELETE", "/api/v1/auth/me", json={"password": "whatever"})
    assert response.status_code == 401


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


def test_refresh_sets_samesite_none_and_secure_cookies_in_production(client: TestClient, db_session, monkeypatch):
    from src.core.config import settings

    _register_verify_and_login(client, "refresh-prod@example.com")
    monkeypatch.setattr(settings, "environment", "production")

    refresh_response = client.post("/api/v1/auth/refresh", headers=_csrf_headers(client))
    assert refresh_response.status_code == 200
    set_cookie = refresh_response.headers.get_list("set-cookie")
    for name in ("access_token", "refresh_token", "csrf_token"):
        cookie = _set_cookie_attrs(set_cookie, name)
        assert "samesite=none" in cookie.lower(), cookie
        assert "secure" in cookie.lower(), cookie

    assert refresh_response.headers.get("x-csrf-token") == client.cookies.get("csrf_token")


def test_logout_clears_session_and_revokes_it(client: TestClient, db_session):
    _register_verify_and_login(client, "logout@example.com")

    logout_response = client.post("/api/v1/auth/logout", headers=_csrf_headers(client))
    assert logout_response.status_code == 200

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_logout_deletes_cookies_with_matching_attributes_in_production(client: TestClient, db_session, monkeypatch):
    """A cookie deletion (Set-Cookie: name=; Max-Age=0) is only reliably
    honored by the browser when its Secure/SameSite/Path attributes
    match how the cookie was originally set -- verifies logout's
    delete_cookie calls were updated in lockstep with login's
    set_cookie calls, not just the happy-path "does /me become 401"
    behavior already covered above."""
    from src.core.config import settings

    _register_verify_and_login(client, "logout-prod@example.com")
    monkeypatch.setattr(settings, "environment", "production")

    logout_response = client.post("/api/v1/auth/logout", headers=_csrf_headers(client))
    assert logout_response.status_code == 200
    set_cookie = logout_response.headers.get_list("set-cookie")

    for name in ("access_token", "refresh_token", "csrf_token"):
        cookie = _set_cookie_attrs(set_cookie, name)
        assert "samesite=none" in cookie.lower(), cookie
        assert "secure" in cookie.lower(), cookie
        assert "max-age=0" in cookie.lower(), cookie


def test_sessions_lists_current_device_as_current(client: TestClient, db_session):
    _register_verify_and_login(client, "sessions@example.com")
    response = client.get("/api/v1/auth/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    assert sessions[0]["last_used_at"] is not None


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
