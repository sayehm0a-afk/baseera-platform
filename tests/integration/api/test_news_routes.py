"""Integration tests for /api/v1/news/* -- real FastAPI routing, real
NewsIntelligenceService, against an in-memory SQLite DB and a fake
IMarketDataProvider/LLM client (no live network call anywhere). Same
session_factory/get_db double-wiring as test_calibrations_routes.py.
"""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user, get_market_provider
from src.core.db.database import Base, get_db
from src.domain.models import (
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    NewsSourceReliability,
    StaffRole,
    Stock,
    User,
)
from src.market_data.providers.market_data_provider import IMarketDataProvider, ProviderHealth
from src.news_intelligence.analyzer import NewsAnalyzer
import src.api.routes.news as news_routes


class _FakeProvider(IMarketDataProvider):
    def __init__(self, items=None):
        self.items = items or []

    async def authenticate(self):
        return True

    async def get_stock_data(self, symbol):
        return {}

    async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
        return []

    async def get_index_data(self, index_name):
        return {}

    async def get_market_news(self, limit=10):
        return self.items[:limit]

    async def health_check(self):
        return ProviderHealth.HEALTHY

    async def disconnect(self):
        pass


class _FakeLLMClient:
    model_name = "gpt-4o-mini"

    def __init__(self, payload):
        self._payload = payload

    async def generate_response(self, messages, **kwargs):
        return {"content": json.dumps(self._payload), "model": self.model_name, "usage": {}}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    staff_user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_current_user] = lambda: staff_user
    main.app.dependency_overrides[get_market_provider] = lambda: _FakeProvider()
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


def _seed_analyzed_event(session_factory, symbol="2222", category=NewsCategory.EARNINGS, sentiment_score=0.7, confidence=85.0, headline="Aramco reports record profit"):
    session = session_factory()
    session.add(Stock(symbol=symbol, name_en="Test Co"))
    event = NewsEvent(
        external_key=f"key-{headline}", headline=headline, source="sahmk", source_reliability_score=0.8,
        published_at=datetime.now(timezone.utc), category=category, sentiment_score=sentiment_score,
        confidence=confidence, analyzed_at=datetime.now(timezone.utc), analysis_model="gpt-4o-mini",
    )
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.COMPANY, symbol=symbol))
    session.commit()
    session.close()


# --- GET /news/{symbol} ---------------------------------------------------


def test_get_symbol_news_returns_persisted_events(client, session_factory):
    _seed_analyzed_event(session_factory)
    response = client.get("/api/v1/news/2222")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["total"] == 1
    assert body["events"][0]["headline"] == "Aramco reports record profit"
    assert body["events"][0]["category"] == "EARNINGS"
    assert body["events"][0]["entities"][0]["symbol"] == "2222"


def test_get_symbol_news_empty_for_unknown_symbol(client, session_factory):
    response = client.get("/api/v1/news/9999")
    assert response.status_code == 200
    assert response.json()["total"] == 0


# --- GET /news/market ------------------------------------------------------


def test_get_market_news_returns_market_wide_events(client, session_factory):
    session = session_factory()
    event = NewsEvent(
        external_key="market-1", headline="SAMA raises interest rates", source="sahmk",
        published_at=datetime.now(timezone.utc), category=NewsCategory.INTEREST_RATES, sentiment_score=-0.3,
        confidence=70.0, analyzed_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.commit()
    session.add(NewsEntity(news_event_id=event.id, entity_type=NewsEntityType.GOVERNMENT, label="SAMA"))
    session.commit()
    session.close()

    response = client.get("/api/v1/news/market")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["events"][0]["headline"] == "SAMA raises interest rates"


def test_get_market_news_excludes_company_specific_events(client, session_factory):
    _seed_analyzed_event(session_factory)
    response = client.get("/api/v1/news/market")
    assert response.status_code == 200
    assert response.json()["total"] == 0


# --- GET /news/sources (staff-only) ---------------------------------------


def test_list_source_reliability(client, session_factory):
    session = session_factory()
    session.add(NewsSourceReliability(source_name="sahmk", reliability_score=0.9, articles_seen=10))
    session.commit()
    session.close()

    response = client.get("/api/v1/news/sources")
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["source_name"] == "sahmk"
    assert sources[0]["reliability_score"] == pytest.approx(0.9)


def test_list_source_reliability_staff_only(client, session_factory):
    non_staff_user = User(email="customer@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff_user
    try:
        response = client.get("/api/v1/news/sources")
    finally:
        main.app.dependency_overrides[get_current_user] = (
            lambda: User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
        )
    assert response.status_code == 403


# --- POST /news/refresh (staff-only) ---------------------------------------


def test_refresh_news_runs_a_real_collection_and_analysis_pass(client, session_factory, monkeypatch):
    headline = "Saudi Aramco reports record quarterly profit"
    provider = _FakeProvider(
        items=[{"headline": headline, "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False}]
    )
    main.app.dependency_overrides[get_market_provider] = lambda: provider

    payload = {
        "entities": [{"entity_type": "COMPANY", "symbol": "2222", "sector": None, "label": None}],
        "category": "EARNINGS", "sentiment_score": 0.7, "sentiment_label": "POSITIVE", "confidence": 85.0,
        "explanation": "Test.", "short_term_impact": 0.2, "medium_term_impact": 0.1, "long_term_impact": 0.0,
        "price_impact": 0.3, "risk_impact": 0.1, "volatility_impact": 0.1,
    }
    real_service_cls = news_routes.NewsIntelligenceService
    monkeypatch.setattr(
        news_routes, "NewsIntelligenceService",
        lambda: real_service_cls(analyzer=NewsAnalyzer(llm_client=_FakeLLMClient(payload))),
    )

    response = client.post("/api/v1/news/refresh", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["collected"] == 1
    assert body["newly_analyzed"] == 1
    assert body["analyzer_available"] is True


def test_refresh_news_honestly_reports_analyzer_unavailable(client, session_factory, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = _FakeProvider(
        items=[{"headline": "Some headline", "symbol": "2222", "timestamp": _now_iso(), "source": "sahmk", "is_synthetic": False}]
    )
    main.app.dependency_overrides[get_market_provider] = lambda: provider

    response = client.post("/api/v1/news/refresh", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["analyzer_available"] is False
    assert body["analysis_unavailable"] == 1


def test_refresh_news_respects_the_limit_field(client, session_factory):
    response = client.post("/api/v1/news/refresh", json={"limit": 5})
    assert response.status_code == 200


def test_refresh_news_rejects_a_limit_above_the_bound(client, session_factory):
    response = client.post("/api/v1/news/refresh", json={"limit": 1000})
    assert response.status_code == 422


def test_refresh_news_staff_only(client, session_factory):
    non_staff_user = User(email="customer@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff_user
    try:
        response = client.post("/api/v1/news/refresh", json={})
    finally:
        main.app.dependency_overrides[get_current_user] = (
            lambda: User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)
        )
    assert response.status_code == 403
