"""Phase 13 P13.6: GET /api/v1/auth/me/export's underlying service.
Proves the export includes the caller's own real data across every
category, excludes secrets/hashes/other users' data, and is
deterministic (same input -> byte-identical JSON) so it's a real,
testable contract rather than a best-effort dump.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import data_export_service
from src.core.db.database import Base
from src.domain.models import (
    Feedback,
    FeedbackCategory,
    Invoice,
    InvoiceStatus,
    Notification,
    NotificationType,
    Payment,
    PaymentStatus,
    Portfolio,
    PortfolioHolding,
    RecommendationHistory,
    Report,
    ReportType,
    Stock,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    SupportTicket,
    User,
    UserSession,
    UserSetting,
    UserWatchlist,
    UserWatchlistItem,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(session):
    u = User(email="export-me@example.com", password_hash="super-secret-hash", full_name="Export Test")
    session.add(u)
    session.commit()
    return u


def test_export_includes_own_profile_without_the_password_hash(session, user):
    export = data_export_service.build_user_data_export(session, user)
    assert export["profile"]["email"] == "export-me@example.com"
    assert export["profile"]["full_name"] == "Export Test"
    assert "password_hash" not in export["profile"]
    assert "password" not in json.dumps(export).lower().replace("password_reset", "")


def test_export_includes_subscription(session, user):
    session.add(
        Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.TRIAL,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
    )
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["subscription"]["plan"] == "TRIAL"
    assert export["subscription"]["status"] == "TRIALING"


def test_export_includes_sessions_without_token_material(session, user):
    session.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti="super-secret-jti-hash",
            family_id="fam-1",
            device_label="Chrome on macOS",
            ip_address="203.0.113.5",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert len(export["sessions"]) == 1
    assert export["sessions"][0]["device_label"] == "Chrome on macOS"
    assert "refresh_token_jti" not in export["sessions"][0]
    assert "family_id" not in export["sessions"][0]
    assert "super-secret-jti-hash" not in json.dumps(export)


def test_export_includes_portfolios_with_holdings_and_alerts(session, user):
    stock = Stock(symbol="2222", name_en="Test Co", sector="Energy")
    session.add(stock)
    session.commit()
    portfolio = Portfolio(user_id=user.id, name="My Portfolio", cash_balance=Decimal("1000.50"))
    session.add(portfolio)
    session.commit()
    session.add(PortfolioHolding(portfolio_id=portfolio.id, stock_id=stock.id, symbol="2222", quantity=10))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert len(export["portfolios"]) == 1
    assert export["portfolios"][0]["name"] == "My Portfolio"
    assert export["portfolios"][0]["cash_balance"] == 1000.50
    assert export["portfolios"][0]["holdings"][0]["symbol"] == "2222"
    assert export["portfolios"][0]["news_alerts"] == []


def test_export_includes_watchlists(session, user):
    stock = Stock(symbol="1010", name_en="Bank Co", sector="Banks")
    session.add(stock)
    session.commit()
    watchlist = UserWatchlist(user_id=user.id, name="Favorites")
    session.add(watchlist)
    session.commit()
    session.add(UserWatchlistItem(watchlist_id=watchlist.id, stock_id=stock.id, symbol="1010"))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["watchlists"][0]["name"] == "Favorites"
    assert export["watchlists"][0]["items"][0]["symbol"] == "1010"


def test_export_includes_settings_preferences(session, user):
    session.add(UserSetting(user_id=user.id, preferences_json={"theme": "dark", "language": "ar"}))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["settings"] == {"theme": "dark", "language": "ar"}


def test_export_includes_notifications(session, user):
    session.add(Notification(user_id=user.id, type=NotificationType.SYSTEM, title="Welcome", body="Hi there"))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["notifications"][0]["title"] == "Welcome"


def test_export_includes_invoices_and_nested_payments(session, user):
    invoice = Invoice(user_id=user.id, amount=Decimal("49.99"), currency="SAR", status=InvoiceStatus.PAID)
    session.add(invoice)
    session.commit()
    session.add(Payment(invoice_id=invoice.id, amount=Decimal("49.99"), status=PaymentStatus.SUCCEEDED))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["invoices"][0]["amount"] == 49.99
    assert export["invoices"][0]["payments"][0]["status"] == "SUCCEEDED"


def test_export_includes_feedback_support_tickets_history_and_reports(session, user):
    session.add(Feedback(user_id=user.id, category=FeedbackCategory.GENERAL, message="Nice app"))
    session.add(SupportTicket(user_id=user.id, subject="Help", message="I need help"))
    session.add(
        RecommendationHistory(user_id=user.id, symbol="2222", recommendation="BUY", confidence=0.9, source="scan")
    )
    session.add(Report(user_id=user.id, report_type=ReportType.DAILY, title="Daily Report"))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["feedback"][0]["message"] == "Nice app"
    assert export["support_tickets"][0]["subject"] == "Help"
    assert export["recommendation_history"][0]["symbol"] == "2222"
    assert export["reports"][0]["title"] == "Daily Report"


def test_export_never_includes_another_users_data(session, user):
    other_user = User(email="other@example.com", password_hash="hashed")
    session.add(other_user)
    session.commit()
    session.add(Feedback(user_id=other_user.id, category=FeedbackCategory.GENERAL, message="Someone else's feedback"))
    session.add(Notification(user_id=other_user.id, type=NotificationType.SYSTEM, title="Not yours", body="b"))
    session.commit()

    export = data_export_service.build_user_data_export(session, user)
    assert export["feedback"] == []
    assert export["notifications"] == []
    assert "Someone else's feedback" not in json.dumps(export)


def test_export_is_deterministic(session, user):
    session.add(Feedback(user_id=user.id, category=FeedbackCategory.GENERAL, message="hi"))
    session.commit()

    first = json.dumps(data_export_service.build_user_data_export(session, user), sort_keys=True)
    second = json.dumps(data_export_service.build_user_data_export(session, user), sort_keys=True)
    assert first == second


def test_export_is_json_serializable(session, user):
    export = data_export_service.build_user_data_export(session, user)
    json.dumps(export)  # raises TypeError if anything isn't JSON-serializable
