"""Unit tests for the Phase 10 M10.8 domain models -- AuditLog,
FeatureFlag, Announcement, GlobalSetting, Notification, UserWatchlist/
UserWatchlistItem, UserSetting, Feedback, SupportTicket, AIRequest,
RecommendationHistory, Report. Round-trip persistence, no network.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    AIRequest,
    AIRequestStatus,
    Announcement,
    AnnouncementSeverity,
    AuditLog,
    Feedback,
    FeedbackCategory,
    FeatureFlag,
    GlobalSetting,
    Notification,
    NotificationType,
    RecommendationHistory,
    Report,
    ReportStatus,
    ReportType,
    Stock,
    SupportTicket,
    SupportTicketStatus,
    User,
    UserSetting,
    UserWatchlist,
    UserWatchlistItem,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(session):
    u = User(email="platform@example.com", password_hash="hashed-value")
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def stock(session):
    s = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
    session.add(s)
    session.commit()
    return s


def test_audit_log_round_trip(session, user):
    log = AuditLog(actor_user_id=user.id, action="user.suspend", target_type="user", target_id=99)
    session.add(log)
    session.commit()

    fetched = session.query(AuditLog).one()
    assert fetched.action == "user.suspend"
    assert fetched.created_at is not None


def test_feature_flag_defaults_disabled_and_key_is_unique(session):
    session.add(FeatureFlag(key="new-dashboard"))
    session.commit()
    assert session.query(FeatureFlag).one().enabled is False

    session.add(FeatureFlag(key="new-dashboard"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_announcement_round_trip(session, user):
    now = datetime.now(timezone.utc)
    session.add(
        Announcement(
            created_by_user_id=user.id,
            title="Scheduled maintenance",
            body="Downtime tonight.",
            severity=AnnouncementSeverity.WARNING,
            starts_at=now,
            ends_at=now + timedelta(hours=2),
        )
    )
    session.commit()

    fetched = session.query(Announcement).one()
    assert fetched.severity == AnnouncementSeverity.WARNING
    assert fetched.is_active is True


def test_global_setting_key_is_unique(session):
    session.add(GlobalSetting(key="maintenance_mode", value="false"))
    session.commit()

    session.add(GlobalSetting(key="maintenance_mode", value="true"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_notification_defaults_unread(session, user):
    session.add(
        Notification(
            user_id=user.id, type=NotificationType.SUBSCRIPTION, title="Trial ending", body="3 days left."
        )
    )
    session.commit()

    fetched = session.query(Notification).one()
    assert fetched.read_at is None


def test_user_watchlist_and_item_round_trip_and_cascade_delete(session, user, stock):
    watchlist = UserWatchlist(user_id=user.id, name="My Picks")
    session.add(watchlist)
    session.commit()

    session.add(UserWatchlistItem(watchlist_id=watchlist.id, stock_id=stock.id, symbol=stock.symbol))
    session.commit()

    assert session.query(UserWatchlistItem).count() == 1

    session.delete(watchlist)
    session.commit()
    assert session.query(UserWatchlistItem).count() == 0


def test_user_watchlist_item_duplicate_stock_rejected(session, user, stock):
    watchlist = UserWatchlist(user_id=user.id, name="My Picks")
    session.add(watchlist)
    session.commit()

    session.add(UserWatchlistItem(watchlist_id=watchlist.id, stock_id=stock.id, symbol=stock.symbol))
    session.commit()

    session.add(UserWatchlistItem(watchlist_id=watchlist.id, stock_id=stock.id, symbol=stock.symbol))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_user_setting_defaults_to_empty_preferences(session, user):
    session.add(UserSetting(user_id=user.id))
    session.commit()

    fetched = session.query(UserSetting).one()
    assert fetched.preferences_json == {}


def test_feedback_allows_anonymous_submission(session):
    session.add(Feedback(user_id=None, category=FeedbackCategory.BUG, message="Something broke."))
    session.commit()
    assert session.query(Feedback).one().user_id is None


def test_support_ticket_defaults_open_and_unassigned(session, user):
    session.add(SupportTicket(user_id=user.id, subject="Help", message="Can't log in."))
    session.commit()

    fetched = session.query(SupportTicket).one()
    assert fetched.status == SupportTicketStatus.OPEN
    assert fetched.assigned_staff_user_id is None


def test_ai_request_round_trip(session, user):
    session.add(
        AIRequest(
            user_id=user.id,
            feature="analyst_report",
            symbol="2222",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=842.5,
            status=AIRequestStatus.SUCCESS,
        )
    )
    session.commit()

    fetched = session.query(AIRequest).one()
    assert fetched.status == AIRequestStatus.SUCCESS
    assert fetched.total_tokens == 150


def test_ai_request_allows_null_user_for_unattended_calls(session):
    session.add(AIRequest(user_id=None, feature="market_scan", status=AIRequestStatus.SUCCESS))
    session.commit()
    assert session.query(AIRequest).one().user_id is None


def test_recommendation_history_round_trip(session, user):
    session.add(
        RecommendationHistory(user_id=user.id, symbol="2222", recommendation="BUY", confidence=0.82, source="ai_screen")
    )
    session.commit()

    fetched = session.query(RecommendationHistory).one()
    assert fetched.recommendation == "BUY"
    assert fetched.viewed_at is not None


def test_report_defaults_pending_and_ungenerated(session, user):
    session.add(Report(user_id=user.id, report_type=ReportType.MONTHLY, title="July Report"))
    session.commit()

    fetched = session.query(Report).one()
    assert fetched.status == ReportStatus.PENDING
    assert fetched.generated_at is None
