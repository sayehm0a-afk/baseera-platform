"""Unit tests for src.news_intelligence.portfolio_alerts."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    AlertSeverity,
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    Notification,
    Portfolio,
    PortfolioAlertType,
    PortfolioNewsAlert,
    Stock,
    User,
)
from src.news_intelligence.portfolio_alerts import (
    PortfolioNewsAlertEngine,
    build_alert_message,
    build_alert_message_ar,
    classify_alert_type,
)


# --- classify_alert_type: pure function -----------------------------------


def test_classify_high_risk_category_overrides_positive_sentiment():
    assert classify_alert_type(NewsCategory.LAWSUIT, 0.9, 90.0) == PortfolioAlertType.HIGH_RISK


def test_classify_very_negative_sentiment_is_high_risk_even_without_a_risk_category():
    assert classify_alert_type(NewsCategory.EARNINGS, -0.8, 90.0) == PortfolioAlertType.HIGH_RISK


def test_classify_strong_positive_sentiment_is_major_opportunity():
    assert classify_alert_type(NewsCategory.EARNINGS, 0.7, 90.0) == PortfolioAlertType.MAJOR_OPPORTUNITY


def test_classify_mild_positive_sentiment_is_upgrade():
    assert classify_alert_type(NewsCategory.EARNINGS, 0.3, 90.0) == PortfolioAlertType.UPGRADE


def test_classify_mild_negative_sentiment_is_downgrade():
    assert classify_alert_type(NewsCategory.GUIDANCE, -0.3, 90.0) == PortfolioAlertType.DOWNGRADE


def test_classify_neutral_sentiment_is_no_alert():
    assert classify_alert_type(NewsCategory.EARNINGS, 0.05, 90.0) is None


def test_classify_below_min_confidence_is_no_alert_regardless_of_sentiment():
    assert classify_alert_type(NewsCategory.LAWSUIT, -0.9, 10.0) is None


def test_build_alert_message_cites_headline_and_category():
    event = NewsEvent(external_key="k", headline="Company X faces lawsuit", source="sahmk", category=NewsCategory.LAWSUIT)
    message = build_alert_message("2222", PortfolioAlertType.HIGH_RISK, event)
    assert "2222" in message
    assert "Company X faces lawsuit" in message
    assert "LAWSUIT" in message


def test_build_alert_message_ar_is_arabic_except_the_verbatim_headline():
    """Pre-launch safety fix (2026-08-22, Priority 2): the Arabic
    companion must not leak the raw English alert-type/category tokens
    -- only the real news headline (untranslated article text) may
    still contain non-Arabic characters."""
    event = NewsEvent(external_key="k", headline="Company X faces lawsuit", source="sahmk", category=NewsCategory.LAWSUIT)
    message_ar = build_alert_message_ar("2222", PortfolioAlertType.HIGH_RISK, event)

    assert "2222" in message_ar
    assert "Company X faces lawsuit" in message_ar
    assert "مخاطرة عالية" in message_ar
    assert "قضية قانونية" in message_ar
    assert "HIGH_RISK" not in message_ar
    assert "LAWSUIT" not in message_ar


# --- PortfolioNewsAlertEngine: full DB integration ------------------------


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
def portfolio(session):
    stock = Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy")
    user = User(email="u@example.com", password_hash="x")
    session.add_all([stock, user])
    session.commit()
    p = Portfolio(user_id=user.id, name="My Portfolio")
    session.add(p)
    session.commit()
    return p


def _analyzed_event(session, symbol, category, sentiment_score, confidence, external_key="k1"):
    event = NewsEvent(
        external_key=external_key, headline=f"News about {symbol}", source="sahmk", category=category,
        sentiment_score=sentiment_score, confidence=confidence, analyzed_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, symbol=symbol))
    session.commit()
    return event


def test_generate_and_persist_creates_a_high_risk_alert_and_a_notification(session, portfolio):
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    alerts = PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, ["2222"])

    assert len(alerts) == 1
    assert alerts[0].alert_type == PortfolioAlertType.HIGH_RISK
    assert alerts[0].severity == AlertSeverity.CRITICAL
    assert alerts[0].id is not None

    assert session.query(PortfolioNewsAlert).count() == 1
    notification = session.query(Notification).one()
    assert notification.user_id == portfolio.user_id


def test_generate_and_persist_populates_arabic_presentation_fields(session, portfolio):
    """Pre-launch safety fix (2026-08-22, Priority 2): both the
    structured PortfolioNewsAlert row and its linked Notification must
    carry a real Arabic companion, not just the legacy English text."""
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, ["2222"])

    alert_row = session.query(PortfolioNewsAlert).one()
    assert alert_row.message_ar is not None
    assert "مخاطرة عالية" in alert_row.message_ar

    notification = session.query(Notification).one()
    assert notification.title_ar is not None
    assert notification.body_ar is not None
    assert "مخاطرة عالية" in notification.title_ar
    assert notification.body_ar == alert_row.message_ar


def test_generate_and_persist_is_idempotent_for_the_same_event(session, portfolio):
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    first = PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, ["2222"])
    second = PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, ["2222"])

    assert len(first) == 1
    assert len(second) == 0
    assert session.query(PortfolioNewsAlert).count() == 1


def test_generate_and_persist_skips_events_that_do_not_clear_the_bar(session, portfolio):
    _analyzed_event(session, "2222", NewsCategory.EARNINGS, 0.05, 90.0)  # too neutral
    alerts = PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, ["2222"])
    assert alerts == []


def test_generate_and_persist_only_considers_held_symbols(session, portfolio):
    _analyzed_event(session, "2010", NewsCategory.LAWSUIT, -0.7, 90.0, external_key="other")
    alerts = PortfolioNewsAlertEngine().generate_and_persist(session, portfolio, ["2222"])  # only holds 2222
    assert alerts == []


def test_generate_and_persist_does_not_create_a_notification_when_portfolio_has_no_user(session):
    stock = Stock(symbol="2222", name_en="Saudi Aramco")
    session.add(stock)
    session.commit()
    ownerless = Portfolio(user_id=None, name="Ownerless")
    session.add(ownerless)
    session.commit()
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    alerts = PortfolioNewsAlertEngine().generate_and_persist(session, ownerless, ["2222"])

    assert len(alerts) == 1
    assert session.query(Notification).count() == 0


def test_generate_and_persist_respects_the_since_filter(session, portfolio):
    old_event = NewsEvent(
        external_key="old", headline="Old lawsuit news", source="sahmk", category=NewsCategory.LAWSUIT,
        sentiment_score=-0.7, confidence=90.0, analyzed_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(old_event)
    session.commit()
    session.add(NewsEntity(news_event_id=old_event.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    session.commit()

    alerts = PortfolioNewsAlertEngine().generate_and_persist(
        session, portfolio, ["2222"], since=datetime.now(timezone.utc) - timedelta(days=1)
    )
    assert alerts == []
