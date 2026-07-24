"""Integration tests for POST /auth/login, POST /auth/refresh."""

import os

from starlette.testclient import TestClient

import main
from src.api.auth.password import hash_password

_SECRET = "test-jwt-secret"
_USERNAME = "admin"
_PASSWORD = "correct horse battery staple"


def setup_function():
    os.environ["SECRET_KEY"] = _SECRET
    os.environ["ADMIN_USERNAME"] = _USERNAME
    os.environ["ADMIN_PASSWORD_HASH"] = hash_password(_PASSWORD, _SECRET)


def _client() -> TestClient:
    return TestClient(main.app)


def test_login_with_correct_credentials_returns_tokens():
    response = _client().post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body and "refresh_token" in body
    assert body["expires_in"] > 0


def test_login_with_wrong_password_is_unauthorized():
    response = _client().post("/auth/login", json={"username": _USERNAME, "password": "wrong password"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_login_with_wrong_username_is_unauthorized():
    response = _client().post("/auth/login", json={"username": "not-admin", "password": _PASSWORD})

    assert response.status_code == 401


def test_login_with_no_admin_configured_is_unauthorized():
    os.environ["ADMIN_USERNAME"] = ""
    os.environ["ADMIN_PASSWORD_HASH"] = ""

    response = _client().post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})

    assert response.status_code == 401


def test_issued_access_token_authenticates_a_protected_route():
    # End-to-end: login -> use the access token as a Bearer credential ->
    # a real protected route (stocks/{symbol} is unauthenticated, so use
    # the analysis technical endpoint's auth dependency directly via the
    # 401-vs-200 contrast instead of depending on seeded data existing).
    from src.api.dependencies import get_current_principal

    login_response = _client().post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
    access_token = login_response.json()["access_token"]

    # Exercise the dependency directly with the real header value FastAPI
    # would parse -- avoids needing seeded DB data just to prove the token
    # itself authenticates successfully.
    principal = get_current_principal(authorization=f"Bearer {access_token}", x_api_key=None)
    assert principal == f"user:{_USERNAME}"


def test_refresh_with_valid_refresh_token_returns_new_access_token():
    login_response = _client().post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
    refresh_token = login_response.json()["refresh_token"]

    response = _client().post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_refresh_with_an_access_token_instead_of_refresh_token_is_rejected():
    login_response = _client().post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
    access_token = login_response.json()["access_token"]

    response = _client().post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


def test_refresh_with_garbage_token_is_rejected():
    response = _client().post("/auth/refresh", json={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401
