"""Integration tests for GET /api/v1/subscriptions/me -- real FastAPI
routing against an in-memory SQLite DB (see conftest.py).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import StaffRole, Subscription, SubscriptionPlan, SubscriptionStatus, User


def _make_customer_with_trial(session: Session) -> User:
    user = User(email="customer@example.com", password_hash="hashed", is_email_verified=True)
    session.add(user)
    session.commit()
    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=14)
    session.add(
        Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.TRIAL,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=trial_ends_at,
            current_period_start=datetime.now(timezone.utc),
            current_period_end=trial_ends_at,
            cancel_at_period_end=False,
        )
    )
    session.commit()
    return user


def _make_customer_without_subscription(session: Session) -> User:
    user = User(email="orphan@example.com", password_hash="hashed", is_email_verified=True)
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def _as(db_session):
    def _set(user: User) -> None:
        main.app.dependency_overrides[get_current_user] = lambda: user

    yield _set
    main.app.dependency_overrides.pop(get_current_user, None)


def test_get_my_subscription_returns_real_trial(client, db_session, _as):
    customer = _make_customer_with_trial(db_session)
    _as(customer)

    response = client.get("/api/v1/subscriptions/me")
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "TRIAL"
    assert body["status"] == "TRIALING"


def test_get_my_subscription_404_for_a_real_customer_with_no_subscription_row(client, db_session, _as):
    """A data-integrity gap (should never happen for a normally-
    registered account -- register() always provisions a trial), kept
    as a 404 for a real customer since it signals something is
    actually wrong, unlike the staff case below."""
    orphan = _make_customer_without_subscription(db_session)
    _as(orphan)

    response = client.get("/api/v1/subscriptions/me")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "subscription_not_found"


def test_get_my_subscription_for_staff_with_no_subscription_row_returns_synthetic_active(
    client, db_session, authenticated_as_staff
):
    """Regression: production confirmed (2026-08-06) that a staff
    account -- created directly by the owner-bootstrap script, never
    through register() -- has no Subscription row at all, since
    provision_trial_subscription() only runs inside register(). This
    used to 404, which reads as something missing/broken; staff
    bypassing subscription checks entirely is already the documented
    design (require_active_subscription()), so this route should say
    so honestly instead."""
    response = client.get("/api/v1/subscriptions/me")
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "STAFF"
    assert body["status"] == "ACTIVE"
    assert body["trial_ends_at"] is None
    assert body["cancel_at_period_end"] is False


def test_get_my_subscription_for_staff_with_a_real_subscription_row_still_returns_it(
    client, db_session, _as
):
    """A staff account that *does* have a real, persisted Subscription
    row (e.g. a staff member who was once a paying customer before
    being granted staff access) must still see their real plan, not
    the synthetic staff fallback."""
    staff = User(
        email="staff-with-sub@example.com", password_hash="hashed",
        is_email_verified=True, is_staff=True, staff_role=StaffRole.ADMIN,
    )
    db_session.add(staff)
    db_session.commit()

    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=14)
    db_session.add(
        Subscription(
            user_id=staff.id,
            plan=SubscriptionPlan.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            trial_ends_at=None,
            current_period_start=datetime.now(timezone.utc),
            current_period_end=trial_ends_at,
            cancel_at_period_end=False,
        )
    )
    db_session.commit()
    _as(staff)

    response = client.get("/api/v1/subscriptions/me")
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "MONTHLY"
    assert body["status"] == "ACTIVE"
