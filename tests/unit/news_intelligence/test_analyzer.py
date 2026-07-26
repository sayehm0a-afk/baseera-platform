"""Unit tests for src.news_intelligence.analyzer.NewsAnalyzer -- a
fake BaseLLMClient stands in for OpenAILLMClient (the same technique
tests/unit/core/llm_abstraction already uses for the client itself);
no real network/OpenAI call in any test here."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import AIRequest, AIRequestStatus, NewsCategory, NewsEntityType, SentimentLabel
from src.news_intelligence.analyzer import NewsAnalyzer
from src.news_intelligence.types import RawNewsItem

_VALID_PAYLOAD = {
    "entities": [{"entity_type": "COMPANY", "symbol": "2222", "sector": "Energy", "label": "Saudi Aramco"}],
    "category": "EARNINGS", "sentiment_score": 0.7, "sentiment_label": "POSITIVE", "confidence": 85.0,
    "explanation": "Strong profit beat.", "short_term_impact": 0.4, "medium_term_impact": 0.3,
    "long_term_impact": 0.1, "price_impact": 0.5, "risk_impact": 0.1, "volatility_impact": 0.2,
}


class _FakeClient:
    model_name = "gpt-4o-mini"

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = 0

    async def generate_response(self, messages, **kwargs):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._response


def _response(payload, model="gpt-4o-mini", usage=None):
    return {"content": json.dumps(payload), "model": model, "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _item(headline="Saudi Aramco reports record quarterly profit", symbol="2222"):
    return RawNewsItem(headline=headline, source="sahmk", is_synthetic=False, symbol=symbol)


# --- availability -----------------------------------------------------


def test_unavailable_without_an_api_key_or_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analyzer = NewsAnalyzer()
    assert analyzer.is_available is False


def test_available_with_an_injected_client():
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(_VALID_PAYLOAD)))
    assert analyzer.is_available is True


@pytest.mark.asyncio
async def test_analyze_returns_none_when_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analyzer = NewsAnalyzer()
    result = await analyzer.analyze(_item())
    assert result is None


# --- successful analysis --------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_parses_a_valid_response():
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(_VALID_PAYLOAD)))
    result = await analyzer.analyze(_item())

    assert result is not None
    assert result.category == NewsCategory.EARNINGS
    assert result.sentiment_score == pytest.approx(0.7)
    assert result.sentiment_label == SentimentLabel.POSITIVE
    assert result.confidence == pytest.approx(85.0)
    assert result.explanation == "Strong profit beat."
    assert result.model == "gpt-4o-mini"
    assert len(result.entities) == 1
    assert result.entities[0].entity_type == NewsEntityType.COMPANY
    assert result.entities[0].symbol == "2222"
    assert result.impact.short_term == pytest.approx(0.4)
    assert result.impact.risk_impact == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_analyze_clamps_out_of_range_values():
    payload = dict(_VALID_PAYLOAD, sentiment_score=5.0, confidence=500.0, price_impact=-5.0)
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(payload)))
    result = await analyzer.analyze(_item())
    assert result.sentiment_score == 1.0
    assert result.confidence == 100.0
    assert result.impact.price_impact == 0.0


@pytest.mark.asyncio
async def test_analyze_falls_back_to_other_and_neutral_for_unknown_enum_values():
    payload = dict(_VALID_PAYLOAD, category="NOT_A_REAL_CATEGORY", sentiment_label="NOT_A_REAL_LABEL")
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(payload)))
    result = await analyzer.analyze(_item())
    assert result.category == NewsCategory.OTHER
    assert result.sentiment_label == SentimentLabel.NEUTRAL


@pytest.mark.asyncio
async def test_analyze_skips_entities_with_an_unrecognized_entity_type():
    payload = dict(_VALID_PAYLOAD, entities=[{"entity_type": "NOT_REAL", "symbol": "2222"}])
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(payload)))
    result = await analyzer.analyze(_item())
    assert result.entities == []


@pytest.mark.asyncio
async def test_analyze_handles_a_markdown_code_fenced_response():
    fenced = "```json\n" + json.dumps(_VALID_PAYLOAD) + "\n```"
    client = _FakeClient(response={"content": fenced, "model": "gpt-4o-mini", "usage": {}})
    analyzer = NewsAnalyzer(llm_client=client)
    result = await analyzer.analyze(_item())
    assert result is not None
    assert result.category == NewsCategory.EARNINGS


# --- failure modes: never fabricate --------------------------------------


@pytest.mark.asyncio
async def test_analyze_returns_none_on_malformed_json():
    client = _FakeClient(response={"content": "this is not json", "model": "gpt-4o-mini", "usage": {}})
    analyzer = NewsAnalyzer(llm_client=client)
    result = await analyzer.analyze(_item())
    assert result is None


@pytest.mark.asyncio
async def test_analyze_returns_none_on_a_json_array_not_an_object():
    client = _FakeClient(response={"content": "[1, 2, 3]", "model": "gpt-4o-mini", "usage": {}})
    analyzer = NewsAnalyzer(llm_client=client)
    result = await analyzer.analyze(_item())
    assert result is None


@pytest.mark.asyncio
async def test_analyze_returns_none_when_the_llm_call_raises():
    client = _FakeClient(raises=ConnectionError("network down"))
    analyzer = NewsAnalyzer(llm_client=client)
    result = await analyzer.analyze(_item())
    assert result is None


# --- AIRequest instrumentation --------------------------------------------


@pytest.mark.asyncio
async def test_analyze_records_a_successful_ai_request(session):
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(_VALID_PAYLOAD)))
    await analyzer.analyze(_item(), session=session, user_id=7)

    request = session.query(AIRequest).one()
    assert request.status == AIRequestStatus.SUCCESS
    assert request.feature == "news_intelligence:analyze"
    assert request.user_id == 7
    assert request.symbol == "2222"
    assert request.total_tokens == 15


@pytest.mark.asyncio
async def test_analyze_records_a_failed_ai_request_on_malformed_json(session):
    client = _FakeClient(response={"content": "not json", "model": "gpt-4o-mini", "usage": {}})
    analyzer = NewsAnalyzer(llm_client=client)
    await analyzer.analyze(_item(), session=session)

    request = session.query(AIRequest).one()
    assert request.status == AIRequestStatus.FAILED


@pytest.mark.asyncio
async def test_analyze_records_a_failed_ai_request_when_the_call_raises(session):
    client = _FakeClient(raises=TimeoutError("slow"))
    analyzer = NewsAnalyzer(llm_client=client)
    await analyzer.analyze(_item(), session=session)

    request = session.query(AIRequest).one()
    assert request.status == AIRequestStatus.FAILED
    assert request.error_message is not None


@pytest.mark.asyncio
async def test_analyze_does_not_record_anything_without_a_session():
    analyzer = NewsAnalyzer(llm_client=_FakeClient(response=_response(_VALID_PAYLOAD)))
    result = await analyzer.analyze(_item())  # no session kwarg
    assert result is not None  # would raise if it tried to use a None session
