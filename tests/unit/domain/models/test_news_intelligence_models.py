"""Unit tests for the News Intelligence Engine's domain models --
NewsEvent, NewsEntity, NewsSourceReliability, PortfolioNewsAlert.
Round-trip persistence, no network.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    AlertSeverity,
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    NewsSourceReliability,
    Portfolio,
    PortfolioAlertType,
    PortfolioNewsAlert,
    SentimentLabel,
    Stock,
    User,
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
def stock(session):
    s = Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy")
    session.add(s)
    session.commit()
    return s


# --- NewsEvent --------------------------------------------------------


def test_news_event_round_trip_with_analysis_fields(session):
    event = NewsEvent(
        external_key="key-1", headline="Aramco reports record profit", source="sahmk",
        source_reliability_score=0.8, published_at=datetime.now(timezone.utc), is_synthetic=False,
        category=NewsCategory.EARNINGS, sentiment_score=0.7, sentiment_label=SentimentLabel.POSITIVE,
        confidence=85.0, explanation="Strong profit beat.", short_term_impact=0.4, medium_term_impact=0.3,
        long_term_impact=0.1, price_impact_score=0.5, risk_impact_score=0.1, volatility_impact_score=0.2,
        analyzed_at=datetime.now(timezone.utc), analysis_model="gpt-4o-mini",
    )
    session.add(event)
    session.commit()

    fetched = session.query(NewsEvent).one()
    assert fetched.category == NewsCategory.EARNINGS
    assert fetched.sentiment_label == SentimentLabel.POSITIVE
    assert fetched.duplicate_of_id is None
    assert fetched.duplicate_count == 0


def test_news_event_external_key_is_unique(session):
    session.add(NewsEvent(external_key="dup-key", headline="A", source="sahmk"))
    session.commit()
    session.add(NewsEvent(external_key="dup-key", headline="B", source="sahmk"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_news_event_can_be_a_duplicate_of_a_canonical_event(session):
    canonical = NewsEvent(external_key="canon", headline="A", source="sahmk")
    session.add(canonical)
    session.commit()

    duplicate = NewsEvent(external_key="dup", headline="A (syndicated)", source="argaam", duplicate_of_id=canonical.id)
    session.add(duplicate)
    session.commit()

    fetched = session.query(NewsEvent).filter_by(external_key="dup").one()
    assert fetched.duplicate_of_id == canonical.id
    assert fetched.category is None  # duplicates are never independently analyzed
    assert fetched.analyzed_at is None


def test_news_event_analysis_fields_default_to_none_when_unanalyzed(session):
    event = NewsEvent(external_key="unanalyzed", headline="A", source="sahmk")
    session.add(event)
    session.commit()

    fetched = session.query(NewsEvent).one()
    assert fetched.category is None
    assert fetched.sentiment_score is None
    assert fetched.analyzed_at is None
    assert fetched.analysis_model is None


# --- NewsEntity ---------------------------------------------------------


def test_news_entity_links_a_company_to_a_stock(session, stock):
    event = NewsEvent(external_key="k1", headline="A", source="sahmk")
    session.add(event)
    session.commit()

    entity = NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, stock_id=stock.id, symbol="2222")
    session.add(entity)
    session.commit()

    fetched_event = session.query(NewsEvent).one()
    assert len(fetched_event.entities) == 1
    assert fetched_event.entities[0].symbol == "2222"
    assert fetched_event.entities[0].stock_id == stock.id


def test_news_entity_supports_market_wide_with_no_stock(session):
    event = NewsEvent(external_key="k2", headline="Interest rates raised", source="sahmk")
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.MARKET_WIDE, label="SAMA rate decision"))
    session.commit()

    fetched = session.query(NewsEntity).one()
    assert fetched.entity_type == NewsEntityType.MARKET_WIDE
    assert fetched.stock_id is None
    assert fetched.symbol is None


def test_one_event_can_have_multiple_entities(session, stock):
    other = Stock(symbol="2010", name_en="SABIC")
    session.add(other)
    session.commit()

    event = NewsEvent(external_key="k3", headline="Merger announced between Aramco and SABIC", source="sahmk")
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, stock_id=stock.id, symbol="2222"))
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, stock_id=other.id, symbol="2010"))
    session.commit()

    fetched = session.query(NewsEvent).one()
    assert {e.symbol for e in fetched.entities} == {"2222", "2010"}


# --- NewsSourceReliability -----------------------------------------------


def test_source_reliability_defaults_and_unique_source_name(session):
    row = NewsSourceReliability(source_name="sahmk")
    session.add(row)
    session.commit()

    fetched = session.query(NewsSourceReliability).one()
    assert fetched.reliability_score == pytest.approx(0.5)
    assert fetched.articles_seen == 0

    session.add(NewsSourceReliability(source_name="sahmk"))
    with pytest.raises(IntegrityError):
        session.commit()


# --- PortfolioNewsAlert ---------------------------------------------------


def test_portfolio_news_alert_round_trip(session, stock):
    user = User(email="u@example.com", password_hash="x")
    session.add(user)
    session.commit()
    portfolio = Portfolio(user_id=user.id, name="My Portfolio")
    session.add(portfolio)
    session.commit()
    event = NewsEvent(external_key="k4", headline="Lawsuit filed", source="sahmk")
    session.add(event)
    session.commit()

    alert = PortfolioNewsAlert(
        portfolio_id=portfolio.id, symbol="2222", news_event_id=event.id, alert_type=PortfolioAlertType.HIGH_RISK,
        severity=AlertSeverity.CRITICAL, message="High risk for 2222.", generated_at=datetime.now(timezone.utc),
    )
    session.add(alert)
    session.commit()

    fetched = session.query(PortfolioNewsAlert).one()
    assert fetched.alert_type == PortfolioAlertType.HIGH_RISK
    assert fetched.severity == AlertSeverity.CRITICAL
    assert fetched.acknowledged_at is None
