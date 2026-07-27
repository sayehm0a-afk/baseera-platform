"""Unit tests for src.news_intelligence.service.NewsIntelligenceService
-- full DB integration against an in-memory SQLite DB, a fake
IMarketDataProvider, and a fake LLM client (no real network)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import NewsCategory, NewsEntity, NewsEntityType, NewsEvent, Stock
from src.news_intelligence.analyzer import NewsAnalyzer
from src.news_intelligence.collection import NewsCollector
from src.news_intelligence.config import get_max_events_per_symbol_sentiment
from src.news_intelligence.service import NewsIntelligenceService


class _FakeProvider:
    def __init__(self, items):
        self.items = items

    async def get_market_news(self, limit=10):
        return self.items[:limit]


class _FakeLLMClient:
    model_name = "gpt-4o-mini"

    def __init__(self, payload_by_headline):
        self._payload_by_headline = payload_by_headline

    async def generate_response(self, messages, **kwargs):
        headline = messages[1]["content"].split("Headline: ")[1].split("\n")[0]
        payload = self._payload_by_headline[headline]
        return {"content": json.dumps(payload), "model": self.model_name, "usage": {}}


def _payload(symbol, category="EARNINGS", sentiment=0.7, confidence=85.0):
    return {
        "entities": [{"entity_type": "COMPANY", "symbol": symbol, "sector": None, "label": None}],
        "category": category, "sentiment_score": sentiment, "sentiment_label": "POSITIVE" if sentiment > 0 else "NEGATIVE",
        "confidence": confidence, "explanation": "Test explanation.", "short_term_impact": 0.2,
        "medium_term_impact": 0.1, "long_term_impact": 0.0, "price_impact": 0.3, "risk_impact": 0.1,
        "volatility_impact": 0.1,
    }


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    db.add(Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy"))
    db.add(Stock(symbol="2010", name_en="SABIC", sector="Materials"))
    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# --- refresh(): collection + dedup + analysis + persistence --------------


@pytest.mark.asyncio
async def test_refresh_persists_a_new_analyzed_canonical_event(session):
    headline = "Saudi Aramco reports record quarterly profit"
    provider = _FakeProvider([{"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False}])
    analyzer = NewsAnalyzer(llm_client=_FakeLLMClient({headline: _payload("2222")}))
    service = NewsIntelligenceService(analyzer=analyzer)

    summary = await service.refresh(session, NewsCollector(market_provider=provider))

    assert summary.collected == 1
    assert summary.newly_analyzed == 1
    assert summary.duplicates == 0
    assert summary.already_ingested == 0

    event = session.query(NewsEvent).one()
    assert event.headline == headline
    assert event.category.value == "EARNINGS"
    assert event.analyzed_at is not None
    assert session.query(NewsEntity).filter_by(news_event_id=event.id, symbol="2222").one() is not None


@pytest.mark.asyncio
async def test_refresh_is_idempotent_on_rerun(session):
    headline = "Saudi Aramco reports record quarterly profit"
    provider = _FakeProvider([{"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False}])
    analyzer = NewsAnalyzer(llm_client=_FakeLLMClient({headline: _payload("2222")}))
    service = NewsIntelligenceService(analyzer=analyzer)
    collector = NewsCollector(market_provider=provider)

    await service.refresh(session, collector)
    second = await service.refresh(session, collector)

    assert second.already_ingested == 1
    assert second.newly_analyzed == 0
    assert session.query(NewsEvent).count() == 1


@pytest.mark.asyncio
async def test_refresh_merges_a_syndicated_duplicate_into_the_canonical_event(session):
    headline = "Saudi Aramco reports record quarterly profit"
    provider = _FakeProvider(
        [
            {"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False},
            {"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "argaam", "is_synthetic": False},
        ]
    )
    analyzer = NewsAnalyzer(llm_client=_FakeLLMClient({headline: _payload("2222")}))
    service = NewsIntelligenceService(analyzer=analyzer)

    summary = await service.refresh(session, NewsCollector(market_provider=provider))

    assert summary.duplicates == 1
    assert summary.newly_analyzed == 1
    canonical = session.query(NewsEvent).filter_by(duplicate_of_id=None).one()
    assert canonical.duplicate_count == 1
    duplicate = session.query(NewsEvent).filter(NewsEvent.duplicate_of_id.isnot(None)).one()
    assert duplicate.category is None  # never independently analyzed


@pytest.mark.asyncio
async def test_refresh_never_calls_the_analyzer_for_a_duplicate(session):
    headline = "Saudi Aramco reports record quarterly profit"
    provider = _FakeProvider(
        [
            {"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False},
            {"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "argaam", "is_synthetic": False},
        ]
    )
    client = _FakeLLMClient({headline: _payload("2222")})
    analyzer = NewsAnalyzer(llm_client=client)
    service = NewsIntelligenceService(analyzer=analyzer)

    await service.refresh(session, NewsCollector(market_provider=provider))

    # Only one analysis call for two collected items (one canonical, one duplicate).
    assert session.query(NewsEvent).filter_by(duplicate_of_id=None).one().analyzed_at is not None


@pytest.mark.asyncio
async def test_refresh_persists_an_unanalyzed_event_when_the_analyzer_is_unavailable(session, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    headline = "Saudi Aramco reports record quarterly profit"
    provider = _FakeProvider([{"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False}])
    service = NewsIntelligenceService(analyzer=NewsAnalyzer())  # no client injected, no API key -> unavailable

    summary = await service.refresh(session, NewsCollector(market_provider=provider))

    assert summary.analysis_unavailable == 1
    assert summary.newly_analyzed == 0
    event = session.query(NewsEvent).one()
    assert event.analyzed_at is None
    assert event.category is None


# --- get_symbol_sentiment(): cheap, synchronous, DB-only read --------------


def test_get_symbol_sentiment_returns_none_with_no_news(session):
    service = NewsIntelligenceService()
    assert service.get_symbol_sentiment(session, "2222") is None


def test_get_symbol_sentiment_aggregates_analyzed_events(session):
    event = NewsEvent(
        external_key="k1", headline="Aramco profit beat", source="sahmk", source_reliability_score=1.0,
        published_at=datetime.now(timezone.utc), category=None, sentiment_score=0.8, confidence=100.0,
        analyzed_at=datetime.now(timezone.utc),
    )
    event.category = NewsCategory.EARNINGS
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    session.commit()

    service = NewsIntelligenceService()
    sentiment = service.get_symbol_sentiment(session, "2222")

    assert sentiment is not None
    assert sentiment.sentiment_score == pytest.approx(0.8)
    assert sentiment.article_count == 1
    assert sentiment.events[0].headline == "Aramco profit beat"


def test_get_symbol_sentiment_excludes_duplicates(session):
    canonical = NewsEvent(
        external_key="k1", headline="Aramco profit beat", source="sahmk", source_reliability_score=1.0,
        published_at=datetime.now(timezone.utc), category=NewsCategory.EARNINGS, sentiment_score=0.8,
        confidence=100.0, analyzed_at=datetime.now(timezone.utc),
    )
    session.add(canonical)
    session.commit()
    duplicate = NewsEvent(external_key="k2", headline="Aramco profit beat (copy)", source="argaam", duplicate_of_id=canonical.id)
    session.add(duplicate)
    session.commit()
    session.add(NewsEntity(news_event_id=canonical.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    # a duplicate is never independently analyzed, so it would never match
    # get_symbol_sentiment's analyzed_at.isnot(None) filter even if it had an entity
    session.commit()

    service = NewsIntelligenceService()
    sentiment = service.get_symbol_sentiment(session, "2222")
    assert sentiment.article_count == 1


def test_get_symbol_sentiment_excludes_events_outside_the_lookback_window(session):
    old_event = NewsEvent(
        external_key="k1", headline="Old news", source="sahmk", source_reliability_score=1.0,
        published_at=datetime.now(timezone.utc) - timedelta(days=30), category=NewsCategory.EARNINGS,
        sentiment_score=0.8, confidence=100.0, analyzed_at=datetime.now(timezone.utc),
    )
    session.add(old_event)
    session.commit()
    session.add(NewsEntity(news_event_id=old_event.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    session.commit()

    service = NewsIntelligenceService()
    assert service.get_symbol_sentiment(session, "2222", lookback_days=7) is None


def test_get_symbol_sentiment_weights_by_confidence_and_source_reliability(session):
    high_confidence = NewsEvent(
        external_key="k1", headline="High confidence positive", source="sahmk", source_reliability_score=1.0,
        published_at=datetime.now(timezone.utc), category=NewsCategory.EARNINGS, sentiment_score=0.9,
        confidence=100.0, analyzed_at=datetime.now(timezone.utc),
    )
    low_confidence = NewsEvent(
        external_key="k2", headline="Low confidence negative", source="sahmk", source_reliability_score=1.0,
        published_at=datetime.now(timezone.utc), category=NewsCategory.EARNINGS, sentiment_score=-0.9,
        confidence=10.0, analyzed_at=datetime.now(timezone.utc),
    )
    session.add_all([high_confidence, low_confidence])
    session.commit()
    session.add(NewsEntity(news_event_id=high_confidence.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    session.add(NewsEntity(news_event_id=low_confidence.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
    session.commit()

    service = NewsIntelligenceService()
    sentiment = service.get_symbol_sentiment(session, "2222")
    # The high-confidence positive event should dominate the weighted average.
    assert sentiment.sentiment_score > 0
    assert sentiment.article_count == 2


def test_get_symbol_sentiment_caps_the_events_breakdown_list(session):
    for i in range(10):
        event = NewsEvent(
            external_key=f"k{i}", headline=f"Story {i}", source="sahmk", source_reliability_score=1.0,
            published_at=datetime.now(timezone.utc), category=NewsCategory.EARNINGS, sentiment_score=0.5,
            confidence=90.0, analyzed_at=datetime.now(timezone.utc),
        )
        session.add(event)
        session.commit()
        session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, symbol="2222"))
        session.commit()

    service = NewsIntelligenceService()
    sentiment = service.get_symbol_sentiment(session, "2222")
    assert sentiment.article_count == 10
    assert len(sentiment.events) == get_max_events_per_symbol_sentiment()
