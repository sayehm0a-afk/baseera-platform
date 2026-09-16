"""Integration tests for POST /api/v1/auth/mfa/* and the MFA branch of
POST /api/v1/auth/login -- optional staff TOTP 2FA (governance audit
2026-09-11, item 7). Same conventions as test_auth_routes.py (real
routing/models against in-memory SQLite, Redis required and skipped
otherwise, rate limiting disabled for the duration of each test).
"""

from typing import Iterator
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from src.api.middleware.rate_limiting import limiter
from src.domain.models import StaffRole, User

pytest.importorskip("redis")


def _redis_available() -> bool:
    try:
        import redis

        return redis.Redis(host="localhost", port=6379, socket_connect_timeout=1).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not available")

_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def _disable_rate_limiting() -> Iterator[None]:
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _csrf_headers(client: TestClient) -> dict:
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}


def _register_verify_login_as_owner(client: TestClient, db_session, email: str) -> User:
    with patch("src.auth.email_verification_service.get_email_sender") as mock_sender:
        response = client.post("/api/v1/auth/register", json={"email": email, "password": _PASSWORD})
        assert response.status_code == 201, response.text
        raw_token = mock_sender.return_value.send_verification_email.call_args[0][1]
    assert client.post("/api/v1/auth/verify-email", json={"token": raw_token}).status_code == 200

    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})
    assert login_response.status_code == 200, login_response.text

    user = db_session.query(User).filter_by(email=email).one()
    user.is_staff = True
    user.staff_role = StaffRole.OWNER
    db_session.commit()
    return user


def _enroll_and_activate(client: TestClient) -> tuple:
    import datetime

    setup_response = client.post("/api/v1/auth/mfa/setup", headers=_csrf_headers(client))
    assert setup_response.status_code == 200, setup_response.text
    secret = setup_response.json()["secret"]

    # Consumes the step ONE BEFORE "now" (still within verify's own
    # +/-1 step drift window) -- the confirmation code and a subsequent
    # login's `pyotp.TOTP(secret).now()` code must land on different
    # steps, or the new TOTP replay guard (User.mfa_last_used_totp_step)
    # would correctly reject the second use as a replay of the first.
    code = pyotp.TOTP(secret).at(datetime.datetime.now(), -1)
    activate_response = client.post(
        "/api/v1/auth/mfa/activate", json={"code": code}, headers=_csrf_headers(client)
    )
    assert activate_response.status_code == 200, activate_response.text
    backup_codes = activate_response.json()["backup_codes"]
    return secret, backup_codes


def test_setup_requires_staff_role(client: TestClient, db_session):
    with patch("src.auth.email_verification_service.get_email_sender") as mock_sender:
        client.post("/api/v1/auth/register", json={"email": "consumer@example.com", "password": _PASSWORD})
        raw_token = mock_sender.return_value.send_verification_email.call_args[0][1]
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    client.post("/api/v1/auth/login", json={"email": "consumer@example.com", "password": _PASSWORD})

    response = client.post("/api/v1/auth/mfa/setup", headers=_csrf_headers(client))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_permission"


def test_setup_returns_a_provisioning_uri_and_secret(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner1@example.com")

    response = client.post("/api/v1/auth/mfa/setup", headers=_csrf_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert "secret" in body
    assert body["provisioning_uri"].startswith("otpauth://totp/")


def test_activate_with_wrong_code_returns_401_and_does_not_enable(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner2@example.com")
    client.post("/api/v1/auth/mfa/setup", headers=_csrf_headers(client))

    response = client.post("/api/v1/auth/mfa/activate", json={"code": "000000"}, headers=_csrf_headers(client))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_mfa_code"

    me = client.get("/api/v1/auth/me")
    assert me.json()["mfa_enabled"] is False


def test_activate_with_correct_code_enables_mfa_and_returns_backup_codes(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner3@example.com")
    _secret, backup_codes = _enroll_and_activate(client)

    assert len(backup_codes) == 10
    me = client.get("/api/v1/auth/me")
    assert me.json()["mfa_enabled"] is True


def test_login_with_mfa_enabled_requires_a_second_step(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner4@example.com")
    secret, _backup_codes = _enroll_and_activate(client)

    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner4@example.com", "password": _PASSWORD}
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["mfa_required"] is True
    assert "mfa_token" in body
    # No session cookie is issued at this point -- a protected route
    # must still reject the caller.
    assert "access_token" not in client.cookies

    me_before_verify = client.get("/api/v1/auth/me")
    assert me_before_verify.status_code == 401


def test_login_verify_with_correct_totp_code_completes_login(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner5@example.com")
    secret, _backup_codes = _enroll_and_activate(client)

    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner5@example.com", "password": _PASSWORD}
    )
    mfa_token = login_response.json()["mfa_token"]

    code = pyotp.TOTP(secret).now()
    verify_response = client.post("/api/v1/auth/mfa/login-verify", json={"mfa_token": mfa_token, "code": code})
    assert verify_response.status_code == 200, verify_response.text
    assert verify_response.json()["email"] == "owner5@example.com"
    assert "access_token" in client.cookies

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200


def test_login_verify_rejects_replay_of_an_already_used_totp_code(client: TestClient, db_session):
    """2026-09-16 audit finding: a TOTP code stays numerically valid for
    +/-1 step (~90s), so a code captured in transit/observed once must
    not be usable to complete a SECOND, independent login (e.g. from a
    different device/session, its own fresh mfa_token) within that same
    window."""
    _register_verify_login_as_owner(client, db_session, "owner5b@example.com")
    secret, _backup_codes = _enroll_and_activate(client)

    client.cookies.clear()
    first_login = client.post(
        "/api/v1/auth/login", json={"email": "owner5b@example.com", "password": _PASSWORD}
    )
    code = pyotp.TOTP(secret).now()
    first_verify = client.post(
        "/api/v1/auth/mfa/login-verify", json={"mfa_token": first_login.json()["mfa_token"], "code": code}
    )
    assert first_verify.status_code == 200, first_verify.text

    # A second, independent login attempt (its own mfa_token) replaying
    # the exact same code must be rejected even though the code is still
    # within its own validity window.
    client.cookies.clear()
    second_login = client.post(
        "/api/v1/auth/login", json={"email": "owner5b@example.com", "password": _PASSWORD}
    )
    replay_response = client.post(
        "/api/v1/auth/mfa/login-verify",
        json={"mfa_token": second_login.json()["mfa_token"], "code": code},
    )
    assert replay_response.status_code == 401
    assert replay_response.json()["error"]["code"] == "invalid_mfa_code"


def test_login_verify_with_a_backup_code_completes_login_exactly_once(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner6@example.com")
    _secret, backup_codes = _enroll_and_activate(client)

    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner6@example.com", "password": _PASSWORD}
    )
    mfa_token = login_response.json()["mfa_token"]

    verify_response = client.post(
        "/api/v1/auth/mfa/login-verify", json={"mfa_token": mfa_token, "code": backup_codes[0]}
    )
    assert verify_response.status_code == 200, verify_response.text

    # The same backup code must not work for a second login.
    client.cookies.clear()
    login_response_2 = client.post(
        "/api/v1/auth/login", json={"email": "owner6@example.com", "password": _PASSWORD}
    )
    mfa_token_2 = login_response_2.json()["mfa_token"]
    reuse_response = client.post(
        "/api/v1/auth/mfa/login-verify", json={"mfa_token": mfa_token_2, "code": backup_codes[0]}
    )
    assert reuse_response.status_code == 401


def test_login_verify_with_wrong_code_is_rejected(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner7@example.com")
    _enroll_and_activate(client)

    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner7@example.com", "password": _PASSWORD}
    )
    mfa_token = login_response.json()["mfa_token"]

    response = client.post("/api/v1/auth/mfa/login-verify", json={"mfa_token": mfa_token, "code": "000000"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_mfa_code"


def test_login_verify_with_a_garbage_mfa_token_is_rejected(client: TestClient, db_session):
    response = client.post(
        "/api/v1/auth/mfa/login-verify", json={"mfa_token": "not-a-real-token", "code": "123456"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_or_expired_token"


def test_disable_requires_correct_password(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner8@example.com")
    _enroll_and_activate(client)

    response = client.post(
        "/api/v1/auth/mfa/disable", json={"password": "wrong-password"}, headers=_csrf_headers(client)
    )
    assert response.status_code == 401
    me = client.get("/api/v1/auth/me")
    assert me.json()["mfa_enabled"] is True


def test_disable_with_correct_password_disables_mfa(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner9@example.com")
    _enroll_and_activate(client)

    response = client.post(
        "/api/v1/auth/mfa/disable", json={"password": _PASSWORD}, headers=_csrf_headers(client)
    )
    assert response.status_code == 200
    assert response.json()["mfa_enabled"] is False

    # A subsequent login no longer requires the second step.
    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner9@example.com", "password": _PASSWORD}
    )
    assert login_response.status_code == 200
    assert "mfa_required" not in login_response.json()


def test_regenerate_backup_codes_invalidates_the_old_set(client: TestClient, db_session):
    _register_verify_login_as_owner(client, db_session, "owner10@example.com")
    _secret, old_codes = _enroll_and_activate(client)

    response = client.post(
        "/api/v1/auth/mfa/backup-codes/regenerate",
        json={"password": _PASSWORD},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200
    new_codes = response.json()["backup_codes"]
    assert set(new_codes) != set(old_codes)

    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner10@example.com", "password": _PASSWORD}
    )
    mfa_token = login_response.json()["mfa_token"]
    old_code_response = client.post(
        "/api/v1/auth/mfa/login-verify", json={"mfa_token": mfa_token, "code": old_codes[0]}
    )
    assert old_code_response.status_code == 401
