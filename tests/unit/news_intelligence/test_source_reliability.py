"""Unit tests for src.news_intelligence.source_reliability.SourceReliabilityService."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.news_intelligence.config import get_default_source_reliability
from src.news_intelligence.source_reliability import SourceReliabilityService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_unknown_source_gets_the_conservative_default(session):
    service = SourceReliabilityService()
    assert service.get_score(session, "never-seen-before") == get_default_source_reliability()


def test_get_or_create_persists_a_new_source(session):
    service = SourceReliabilityService()
    row = service.get_or_create(session, "sahmk")
    assert row.source_name == "sahmk"
    assert row.reliability_score == get_default_source_reliability()
    assert row.articles_seen == 0


def test_get_or_create_is_idempotent(session):
    service = SourceReliabilityService()
    first = service.get_or_create(session, "sahmk")
    second = service.get_or_create(session, "sahmk")
    assert first.id == second.id


def test_record_article_seen_increments_the_count(session):
    service = SourceReliabilityService()
    service.record_article_seen(session, "sahmk")
    service.record_article_seen(session, "sahmk")
    row = service.get_or_create(session, "sahmk")
    assert row.articles_seen == 2


def test_record_article_seen_does_not_change_the_reliability_score(session):
    service = SourceReliabilityService()
    service.set_reliability(session, "sahmk", 0.9)
    service.record_article_seen(session, "sahmk")
    assert service.get_score(session, "sahmk") == pytest.approx(0.9)


def test_set_reliability_is_clamped_to_zero_one(session):
    service = SourceReliabilityService()
    service.set_reliability(session, "sahmk", 5.0)
    assert service.get_score(session, "sahmk") == 1.0
    service.set_reliability(session, "sahmk", -5.0)
    assert service.get_score(session, "sahmk") == 0.0


def test_set_reliability_records_notes(session):
    service = SourceReliabilityService()
    row = service.set_reliability(session, "sahmk", 0.7, notes="Verified Tadawul-licensed provider.")
    assert row.notes == "Verified Tadawul-licensed provider."
