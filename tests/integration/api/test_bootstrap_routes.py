"""Integration tests for POST /api/v1/bootstrap/owner.

Uses the shared `client`/`db_session` fixtures (tests/integration/api/
conftest.py) -- a real FastAPI TestClient against an in-memory SQLite
DB, exercised through the actual route/dependency stack (not calling
bootstrap_service directly, which tests/unit/auth/test_bootstrap_service.py
already covers).
"""

from src.core.config import settings
from src.domain.models import StaffRole, User


def test_missing_token_is_rejected(client, db_session):
    resp = client.post(
        "/api/v1/bootstrap/owner",
        json={"email": "owner@example.com", "password": "a-strong-password-123"},
    )
    assert resp.status_code == 401
    assert db_session.query(User).count() == 0


def test_wrong_token_is_rejected(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_token", "the-real-token")
    resp = client.post(
        "/api/v1/bootstrap/owner",
        headers={"x-bootstrap-token": "not-the-real-token"},
        json={"email": "owner@example.com", "password": "a-strong-password-123"},
    )
    assert resp.status_code == 401
    assert db_session.query(User).count() == 0


def test_route_is_disabled_when_no_token_is_configured(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_token", None)
    resp = client.post(
        "/api/v1/bootstrap/owner",
        headers={"x-bootstrap-token": "anything"},
        json={"email": "owner@example.com", "password": "a-strong-password-123"},
    )
    assert resp.status_code == 401
    assert db_session.query(User).count() == 0


def test_correct_token_creates_the_first_owner(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_token", "the-real-token")
    resp = client.post(
        "/api/v1/bootstrap/owner",
        headers={"x-bootstrap-token": "the-real-token"},
        json={"email": "owner@example.com", "password": "a-strong-password-123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "owner@example.com"
    assert body["is_staff"] is True
    assert body["staff_role"] == "OWNER"
    assert "password" not in body

    user = db_session.query(User).filter_by(email="owner@example.com").one()
    assert user.staff_role == StaffRole.OWNER


def test_correct_token_but_already_bootstrapped_is_refused(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_token", "the-real-token")
    db_session.add(User(email="existing-owner@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER))
    db_session.commit()

    resp = client.post(
        "/api/v1/bootstrap/owner",
        headers={"x-bootstrap-token": "the-real-token"},
        json={"email": "new-owner@example.com", "password": "a-strong-password-123"},
    )
    assert resp.status_code == 403
    assert db_session.query(User).count() == 1


def test_password_shorter_than_the_elevated_minimum_is_rejected(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_token", "the-real-token")
    resp = client.post(
        "/api/v1/bootstrap/owner",
        headers={"x-bootstrap-token": "the-real-token"},
        json={"email": "owner@example.com", "password": "short1"},
    )
    assert resp.status_code == 422
    assert db_session.query(User).count() == 0
