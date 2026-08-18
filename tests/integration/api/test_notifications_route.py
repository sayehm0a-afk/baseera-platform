"""Integration tests for GET/POST /api/v1/notifications -- the first
consumer surface for the existing `Notification` table (RADAR-C Phase I).
Mirrors the ownership-scoping pattern in test_watchlist_route.py: every
route resolves rows strictly by `current_user.id`.
"""

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import Notification, NotificationType, User


@pytest.fixture
def as_user(db_session):
    user = User(email="user@example.com", password_hash="hashed", is_staff=False)
    db_session.add(user)
    db_session.commit()
    main.app.dependency_overrides[get_current_user] = lambda: user
    yield user


@pytest.fixture
def other_user(db_session):
    user = User(email="other@example.com", password_hash="hashed", is_staff=False)
    db_session.add(user)
    db_session.commit()
    return user


def _add_notification(db_session, user_id, title="عنوان", body="نص", read=False):
    from datetime import datetime, timezone

    n = Notification(
        user_id=user_id, type=NotificationType.MARKET_ALERT, title=title, body=body,
        read_at=datetime.now(timezone.utc) if read else None,
    )
    db_session.add(n)
    db_session.commit()
    return n


def test_list_notifications_requires_authentication(client, db_session):
    response = client.get("/api/v1/notifications")
    assert response.status_code == 401


def test_list_notifications_is_empty_for_a_new_user(client, db_session, as_user):
    response = client.get("/api/v1/notifications")
    assert response.status_code == 200
    body = response.json()
    assert body["notifications"] == []
    assert body["unread_count"] == 0


def test_list_notifications_returns_the_users_own_notifications_newest_first(client, db_session, as_user):
    _add_notification(db_session, as_user.id, title="أول")
    _add_notification(db_session, as_user.id, title="ثاني")

    response = client.get("/api/v1/notifications")

    assert response.status_code == 200
    titles = [n["title"] for n in response.json()["notifications"]]
    assert titles == ["ثاني", "أول"]


def test_list_notifications_counts_only_unread(client, db_session, as_user):
    _add_notification(db_session, as_user.id, read=True)
    _add_notification(db_session, as_user.id, read=False)
    _add_notification(db_session, as_user.id, read=False)

    response = client.get("/api/v1/notifications")

    assert response.json()["unread_count"] == 2


def test_list_notifications_never_returns_another_users_notifications(client, db_session, as_user, other_user):
    _add_notification(db_session, other_user.id)

    response = client.get("/api/v1/notifications")

    assert response.status_code == 200
    assert response.json()["notifications"] == []
    assert response.json()["unread_count"] == 0


def test_mark_notification_read_sets_read_at(client, db_session, as_user):
    n = _add_notification(db_session, as_user.id)

    response = client.post(f"/api/v1/notifications/{n.id}/read")

    assert response.status_code == 200
    assert response.json()["read_at"] is not None

    db_session.refresh(n)
    assert n.read_at is not None


def test_mark_notification_read_is_idempotent(client, db_session, as_user):
    n = _add_notification(db_session, as_user.id)

    first = client.post(f"/api/v1/notifications/{n.id}/read")
    second = client.post(f"/api/v1/notifications/{n.id}/read")

    assert first.json()["read_at"] == second.json()["read_at"]


def test_mark_notification_read_404_for_unknown_id(client, db_session, as_user):
    response = client.post("/api/v1/notifications/9999/read")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "notification_not_found"


def test_mark_notification_read_404_for_another_users_notification(client, db_session, as_user, other_user):
    n = _add_notification(db_session, other_user.id)

    response = client.post(f"/api/v1/notifications/{n.id}/read")

    assert response.status_code == 404
    db_session.refresh(n)
    assert n.read_at is None  # never touched


def test_mark_all_notifications_read(client, db_session, as_user):
    _add_notification(db_session, as_user.id)
    _add_notification(db_session, as_user.id)

    response = client.post("/api/v1/notifications/read-all")

    assert response.status_code == 200
    assert "message" in response.json()

    follow_up = client.get("/api/v1/notifications")
    assert follow_up.json()["unread_count"] == 0


def test_mark_all_notifications_read_does_not_touch_another_users_notifications(
    client, db_session, as_user, other_user
):
    other_notification = _add_notification(db_session, other_user.id)

    client.post("/api/v1/notifications/read-all")

    db_session.refresh(other_notification)
    assert other_notification.read_at is None
