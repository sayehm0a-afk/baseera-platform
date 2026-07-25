"""Integration tests for /api/v1/admin/* -- real FastAPI routing
against in-memory SQLite. get_current_user is overridden per-test
(via a mutable holder so a single override can return different users
across requests in one test) rather than a real login flow, matching
the approach already used for staff-gated routes in
test_backtests_routes.py/test_calibrations_routes.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user
from src.core.db.database import Base, get_db
from src.domain.models import (
    AIRequest,
    AIRequestStatus,
    StaffRole,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    User,
    UserSession,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    # SQLite does not enforce foreign keys by default -- turned on here
    # so test_owner_cannot_delete_a_user_with_non_cascading_related_records
    # actually exercises the same FK-RESTRICT behavior Postgres already
    # enforces in production (verified separately via the real migrations).
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    def _override_get_db():
        yield db

    main.app.dependency_overrides[get_db] = _override_get_db
    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def owner(session) -> User:
    u = User(email="owner@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def admin(session) -> User:
    u = User(email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def customer(session) -> User:
    u = User(email="customer@example.com", password_hash="hashed", is_email_verified=True)
    session.add(u)
    session.commit()
    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(
        Subscription(
            user_id=u.id,
            plan=SubscriptionPlan.TRIAL,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=trial_ends_at,
            current_period_start=datetime.now(timezone.utc),
            current_period_end=trial_ends_at,
        )
    )
    session.commit()
    return u


def _as(user: User) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture
def client(session) -> Iterator[TestClient]:
    yield TestClient(main.app)


# --- permission gating --------------------------------------------------


def test_non_staff_customer_is_rejected_from_every_admin_surface(client, customer):
    _as(customer)
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/subscriptions").status_code == 403
    assert client.get("/api/v1/admin/sessions").status_code == 403
    assert client.get("/api/v1/admin/announcements").status_code == 403
    assert client.get("/api/v1/admin/feature-flags").status_code == 403
    assert client.get("/api/v1/admin/audit-log").status_code == 403
    assert client.get("/api/v1/admin/usage/ai").status_code == 403
    assert client.get("/api/v1/admin/analytics").status_code == 403
    assert client.get("/api/v1/admin/system/health").status_code == 403


def test_admin_cannot_delete_a_user_only_owner_can(client, admin, customer):
    _as(admin)
    response = client.delete(f"/api/v1/admin/users/{customer.id}")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_permission"


# --- users ---------------------------------------------------------------


def test_list_and_get_user(client, admin, customer):
    _as(admin)
    listing = client.get("/api/v1/admin/users")
    assert listing.status_code == 200
    assert listing.json()["total"] == 2  # admin + customer

    response = client.get(f"/api/v1/admin/users/{customer.id}")
    assert response.status_code == 200
    assert response.json()["email"] == "customer@example.com"


def test_get_unknown_user_404s(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/users/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"


def test_suspend_and_unsuspend_user(client, admin, customer):
    _as(admin)
    suspend = client.post(f"/api/v1/admin/users/{customer.id}/suspend")
    assert suspend.status_code == 200
    assert suspend.json()["is_active"] is False

    unsuspend = client.post(f"/api/v1/admin/users/{customer.id}/unsuspend")
    assert unsuspend.status_code == 200
    assert unsuspend.json()["is_active"] is True


def test_owner_can_delete_a_user_with_no_related_records(client, owner, session):
    plain_user = User(email="deleteme@example.com", password_hash="hashed")
    session.add(plain_user)
    session.commit()
    user_id = plain_user.id

    _as(owner)
    response = client.delete(f"/api/v1/admin/users/{user_id}")
    assert response.status_code == 200

    assert client.get(f"/api/v1/admin/users/{user_id}").status_code == 404


def test_owner_can_delete_a_user_whose_only_related_row_is_a_cascading_subscription(client, owner, customer, session):
    # customer (from the fixture) has a Subscription, which
    # User.subscription's own cascade="all, delete-orphan" handles --
    # confirm that alone does not block deletion.
    _as(owner)
    response = client.delete(f"/api/v1/admin/users/{customer.id}")
    assert response.status_code == 200


def test_owner_cannot_delete_a_user_with_non_cascading_related_records(client, owner, admin, session):
    from src.admin.audit_log import record_admin_action

    # admin is the actor of a real AuditLog row -- AuditLog.actor_user_id
    # has no cascade configured, so the database's own FK RESTRICT must
    # block this deletion rather than silently discarding the audit trail.
    record_admin_action(session, admin.id, "user.suspend", "user", target_id=999)

    _as(owner)
    response = client.delete(f"/api/v1/admin/users/{admin.id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "user_has_related_records"


def test_audit_log_records_suspend_action(client, admin, customer):
    _as(admin)
    client.post(f"/api/v1/admin/users/{customer.id}/suspend")

    logs = client.get("/api/v1/admin/audit-log").json()["logs"]
    assert any(log["action"] == "user.suspend" and log["target_id"] == customer.id for log in logs)


# --- subscriptions ---------------------------------------------------------


def test_list_and_get_subscription(client, admin, customer):
    _as(admin)
    listing = client.get("/api/v1/admin/subscriptions")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    response = client.get(f"/api/v1/admin/subscriptions/{customer.id}")
    assert response.status_code == 200
    assert response.json()["plan"] == "TRIAL"


def test_extend_trial(client, admin, customer):
    _as(admin)
    before = client.get(f"/api/v1/admin/subscriptions/{customer.id}").json()["trial_ends_at"]

    response = client.post(f"/api/v1/admin/subscriptions/{customer.id}/extend-trial", json={"additional_days": 7})
    assert response.status_code == 200
    after = response.json()["trial_ends_at"]
    assert after > before


def test_activate_subscription(client, admin, customer):
    _as(admin)
    response = client.post(
        f"/api/v1/admin/subscriptions/{customer.id}/activate", json={"plan": "MONTHLY", "period_days": 30}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "MONTHLY"
    assert body["status"] == "ACTIVE"


def test_activate_subscription_rejects_invalid_plan(client, admin, customer):
    _as(admin)
    response = client.post(
        f"/api/v1/admin/subscriptions/{customer.id}/activate", json={"plan": "TRIAL", "period_days": 30}
    )
    assert response.status_code == 422  # fails schema pattern validation


def test_subscription_404_for_unknown_user(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/subscriptions/999999")
    assert response.status_code == 404


# --- sessions --------------------------------------------------------------


def test_list_all_active_sessions_and_revoke(client, admin, customer, session):
    future = datetime.now(timezone.utc) + timedelta(days=30)
    user_session = UserSession(
        user_id=customer.id, refresh_token_jti="jti-1", family_id="fam-1", expires_at=future
    )
    session.add(user_session)
    session.commit()

    _as(admin)
    listing = client.get("/api/v1/admin/sessions")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    response = client.delete(f"/api/v1/admin/sessions/{user_session.id}")
    assert response.status_code == 200

    listing_after = client.get("/api/v1/admin/sessions")
    assert listing_after.json()["total"] == 0


def test_revoke_unknown_session_404s(client, admin):
    _as(admin)
    response = client.delete("/api/v1/admin/sessions/999999")
    assert response.status_code == 404


# --- announcements -----------------------------------------------------


def test_announcement_lifecycle(client, admin):
    _as(admin)
    create = client.post(
        "/api/v1/admin/announcements",
        json={
            "title": "Maintenance",
            "body": "Downtime tonight",
            "severity": "WARNING",
            "starts_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert create.status_code == 201
    announcement_id = create.json()["id"]
    assert create.json()["is_active"] is True

    listing = client.get("/api/v1/admin/announcements")
    assert len(listing.json()["announcements"]) == 1

    update = client.patch(f"/api/v1/admin/announcements/{announcement_id}", json={"is_active": False})
    assert update.status_code == 200
    assert update.json()["is_active"] is False

    delete = client.delete(f"/api/v1/admin/announcements/{announcement_id}")
    assert delete.status_code == 200
    assert client.get("/api/v1/admin/announcements").json()["announcements"] == []


def test_announcement_404_for_unknown_id(client, admin):
    _as(admin)
    response = client.patch("/api/v1/admin/announcements/999999", json={"is_active": False})
    assert response.status_code == 404


# --- feature flags -------------------------------------------------------


def test_feature_flag_lifecycle(client, admin):
    _as(admin)
    create = client.post("/api/v1/admin/feature-flags", json={"key": "new-dashboard", "enabled": False})
    assert create.status_code == 201

    duplicate = client.post("/api/v1/admin/feature-flags", json={"key": "new-dashboard", "enabled": True})
    assert duplicate.status_code == 409

    update = client.patch("/api/v1/admin/feature-flags/new-dashboard", json={"enabled": True})
    assert update.status_code == 200
    assert update.json()["enabled"] is True

    listing = client.get("/api/v1/admin/feature-flags")
    assert len(listing.json()["feature_flags"]) == 1


def test_feature_flag_404_for_unknown_key(client, admin):
    _as(admin)
    response = client.patch("/api/v1/admin/feature-flags/does-not-exist", json={"enabled": True})
    assert response.status_code == 404


# --- usage / analytics / system health -----------------------------------


def test_ai_usage_summary(client, admin, customer, session):
    session.add(AIRequest(user_id=customer.id, feature="analyst_narration:technical_reasoning", status=AIRequestStatus.SUCCESS, total_tokens=100))
    session.add(AIRequest(user_id=customer.id, feature="analyst_narration:technical_reasoning", status=AIRequestStatus.FAILED))
    session.commit()

    _as(admin)
    response = client.get("/api/v1/admin/usage/ai")
    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 2
    assert body["success_count"] == 1
    assert body["failed_count"] == 1
    assert body["by_feature"]["analyst_narration:technical_reasoning"] == 2


def test_analytics(client, admin, customer):
    _as(admin)
    response = client.get("/api/v1/admin/analytics")
    assert response.status_code == 200
    body = response.json()
    assert body["total_users"] == 2  # admin + customer
    assert body["subscriptions_by_status"] == {"TRIALING": 1}
    assert body["subscriptions_by_plan"] == {"TRIAL": 1}


def test_system_health(client, admin):
    _as(admin)
    response = client.get("/api/v1/admin/system/health")
    assert response.status_code == 200
    assert response.json()["details"]["database"] == "healthy"
