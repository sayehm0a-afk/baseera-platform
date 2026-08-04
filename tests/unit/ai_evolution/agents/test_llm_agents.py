"""Unit tests for E7's News/Sentiment/Judge agents -- a fake
`LLMAdapter` stands in for the real network client (the same technique
`tests/unit/analysis/analyst/test_openai_llm_adapter.py` already
uses); no real OpenAI call anywhere. `_load_symbol_sentiment` is
monkeypatched to a hand-built fixture -- `NewsIntelligenceService`'s
own DB-read logic is already covered by that package's own tests, so
these tests focus on the LLM-safety behavior these agents add on top.
"""

import pytest

from src.ai_evolution.agents import llm_agents as llm_agents_module
from src.ai_evolution.agents.llm_agents import JudgeAgent, NewsAnalystAgent, SentimentAnalystAgent
from src.ai_evolution.agents.types import AgentOpinionResult
from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationRequest, LLMGenerationResult
from src.domain.models import AgentStance, NewsCategory
from src.news_intelligence.types import NewsEventSummary, SymbolNewsSentiment


class _FakeAdapter(LLMAdapter):
    name = "fake"

    def __init__(self, response_text="A grounded rephrasing."):
        self._response_text = response_text
        self.calls = 0

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        self.calls += 1
        return LLMGenerationResult(text=self._response_text, model="fake-model", finish_reason="stop")


def _sentiment(score=0.5, article_count=2):
    return SymbolNewsSentiment(
        sentiment_score=score,
        article_count=article_count,
        events=[
            NewsEventSummary(
                news_event_id=1, headline="Strong quarterly earnings", category=NewsCategory.EARNINGS,
                sentiment_score=score, confidence=80.0, impact_points=5.0,
            )
        ],
    )


@pytest.fixture
def fake_session():
    return object()  # never touched directly; _load_symbol_sentiment is monkeypatched


class TestNewsAnalystAgent:
    @pytest.mark.asyncio
    async def test_unavailable_when_no_llm_adapter(self, fake_session):
        agent = NewsAnalystAgent(llm_adapter=None)
        result = await agent.analyze(fake_session, "2222")
        assert result.stance is AgentStance.UNAVAILABLE
        assert result.used_llm is False

    @pytest.mark.asyncio
    async def test_unavailable_when_no_news_found(self, fake_session, monkeypatch):
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: None)
        agent = NewsAnalystAgent(llm_adapter=_FakeAdapter())
        result = await agent.analyze(fake_session, "2222")
        assert result.stance is AgentStance.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_bullish_stance_from_positive_sentiment(self, fake_session, monkeypatch):
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: _sentiment(score=0.6))
        agent = NewsAnalystAgent(llm_adapter=_FakeAdapter())
        result = await agent.analyze(fake_session, "2222")
        assert result.stance is AgentStance.BULLISH
        assert result.used_llm is True
        assert result.reasoning == "A grounded rephrasing."

    @pytest.mark.asyncio
    async def test_bearish_stance_from_negative_sentiment(self, fake_session, monkeypatch):
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: _sentiment(score=-0.6))
        agent = NewsAnalystAgent(llm_adapter=_FakeAdapter())
        result = await agent.analyze(fake_session, "2222")
        assert result.stance is AgentStance.BEARISH

    @pytest.mark.asyncio
    async def test_falls_back_to_structured_summary_when_llm_returns_nothing(self, fake_session, monkeypatch):
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: _sentiment(score=0.6))
        agent = NewsAnalystAgent(llm_adapter=_FakeAdapter(response_text=""))
        result = await agent.analyze(fake_session, "2222")
        assert result.used_llm is False
        assert "article" in result.reasoning.lower()


class TestSentimentAnalystAgent:
    @pytest.mark.asyncio
    async def test_unavailable_when_no_llm_adapter(self, fake_session):
        agent = SentimentAnalystAgent(llm_adapter=None)
        result = await agent.analyze(fake_session, "2222")
        assert result.stance is AgentStance.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_neutral_stance_from_middling_sentiment(self, fake_session, monkeypatch):
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: _sentiment(score=0.05))
        agent = SentimentAnalystAgent(llm_adapter=_FakeAdapter())
        result = await agent.analyze(fake_session, "2222")
        assert result.stance is AgentStance.NEUTRAL


class TestJudgeAgent:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_no_adapter(self):
        judge = JudgeAgent(llm_adapter=None)
        opinions = [AgentOpinionResult(agent_name="Technical Analyst", stance=AgentStance.BULLISH, confidence=70.0, reasoning="r")]
        explanation = await judge.synthesize("2222", opinions, "BUY", 0.6)
        assert explanation == ""

    @pytest.mark.asyncio
    async def test_returns_grounded_completion_when_adapter_available(self):
        judge = JudgeAgent(llm_adapter=_FakeAdapter(response_text="The panel favored BUY."))
        opinions = [
            AgentOpinionResult(agent_name="Technical Analyst", stance=AgentStance.BULLISH, confidence=70.0, reasoning="r"),
            AgentOpinionResult(agent_name="Risk Manager", stance=AgentStance.BEARISH, confidence=60.0, reasoning="r2"),
        ]
        explanation = await judge.synthesize("2222", opinions, "BUY", 0.55)
        assert explanation == "The panel favored BUY."
