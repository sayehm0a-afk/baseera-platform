"""Unit tests for src.news_intelligence.watchlist_alerts -- the
watchlist-side mirror of test_portfolio_alerts.py. `classify_alert_type`/
`build_alert_message` are reused verbatim from portfolio_alerts.py and
already covered there; these tests focus on `WatchlistNewsAlertEngine`
itself (persistence, idempotency, symbol scoping, since-filter,
notification creation)."""

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
    NotificationType,
    PortfolioAlertType,
    Stock,
    User,
    UserWatchlist,
    WatchlistNewsAlert,
)
from src.news_intelligence.watchlist_alerts import WatchlistNewsAlertEngine


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
def watchlist(session):
    stock = Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy")
    user = User(email="u@example.com", password_hash="x")
    session.add_all([stock, user])
    session.commit()
    w = UserWatchlist(user_id=user.id, name="My Watchlist")
    session.add(w)
    session.commit()
    return w


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


def test_generate_and_persist_creates_a_high_risk_alert_and_a_notification(session, watchlist):
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    alerts = WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, ["2222"])

    assert len(alerts) == 1
    assert alerts[0].alert_type == PortfolioAlertType.HIGH_RISK
    assert alerts[0].severity == AlertSeverity.CRITICAL
    assert alerts[0].id is not None

    assert session.query(WatchlistNewsAlert).count() == 1
    notification = session.query(Notification).one()
    assert notification.user_id == watchlist.user_id
    assert notification.type == NotificationType.MARKET_ALERT


def test_generate_and_persist_populates_arabic_presentation_fields(session, watchlist):
    """Pre-launch safety fix (2026-08-22, Priority 2)."""
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, ["2222"])

    alert_row = session.query(WatchlistNewsAlert).one()
    assert alert_row.message_ar is not None
    assert "مخاطرة عالية" in alert_row.message_ar

    notification = session.query(Notification).one()
    assert notification.title_ar is not None
    assert notification.body_ar == alert_row.message_ar


def test_generate_and_persist_is_idempotent_for_the_same_event(session, watchlist):
    _analyzed_event(session, "2222", NewsCategory.LAWSUIT, -0.7, 90.0)

    first = WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, ["2222"])
    second = WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, ["2222"])

    assert len(first) == 1
    assert len(second) == 0
    assert session.query(WatchlistNewsAlert).count() == 1


def test_generate_and_persist_skips_events_that_do_not_clear_the_bar(session, watchlist):
    _analyzed_event(session, "2222", NewsCategory.EARNINGS, 0.05, 90.0)  # too neutral
    alerts = WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, ["2222"])
    assert alerts == []


def test_generate_and_persist_only_considers_watched_symbols(session, watchlist):
    _analyzed_event(session, "2010", NewsCategory.LAWSUIT, -0.7, 90.0, external_key="other")
    alerts = WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, ["2222"])  # only watches 2222
    assert alerts == []


def test_generate_and_persist_respects_the_since_filter(session, watchlist):
    old_event = NewsEvent(
        external_key="old", headline="Old lawsuit news", source="sahmk", category=NewsCategory.LAWSUIT,
        sentiment_score=-0.7, confidence=90.0, analyzed_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(old_event)
    session.commit()
    session.add(NewsEntity(news_event_id=old_event.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    session.commit()

    alerts = WatchlistNewsAlertEngine().generate_and_persist(
        session, watchlist, ["2222"], since=datetime.now(timezone.utc) - timedelta(days=1)
    )
    assert alerts == []
