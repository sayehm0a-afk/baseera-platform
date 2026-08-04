"""Unit tests for E7's AgentPanelOrchestrator -- real SQLAlchemy ORM
against an in-memory SQLite DB, a fake LLM adapter (no real OpenAI
call), and real DebateEngine/VotingSystem bookkeeping.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.agents import orchestrator as orchestrator_module
from src.ai_evolution.agents.orchestrator import AgentPanelOrchestrator
from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationRequest, LLMGenerationResult
from src.core.db.database import Base
from src.domain.models import AgentOpinion, DebateSession, RecommendationLabel, RecommendationSnapshot, Stock
from tests.unit.market_intelligence._fixtures import make_breakdown, make_decision


class _FakeAdapter(LLMAdapter):
    name = "fake"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        return LLMGenerationResult(text="A grounded explanation.", model="fake-model", finish_reason="stop")


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stock(session):
    row = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
    session.add(row)
    session.commit()
    return row


def _snapshot(session, stock):
    row = RecommendationSnapshot(
        stock_id=stock.id, symbol=stock.symbol, evaluated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        market_price_at_evaluation=100.0, recommendation=RecommendationLabel.BUY, total_score=60.0,
        confidence_score=70.0, engine_version="1.0.0", source="live_scan",
    )
    session.add(row)
    session.flush()
    return row


def _aligned_breakdown():
    """Technical and Fundamental agree -- no material disagreement."""
    return [
        make_breakdown(category="Technical Analysis", points=10.0),
        make_breakdown(category="Fundamental Analysis", points=8.0),
    ]


def _conflicting_breakdown():
    """Technical vs Fundamental spread >= MODERATE_TENSION_THRESHOLD (15)."""
    return [
        make_breakdown(category="Technical Analysis", points=20.0),
        make_breakdown(category="Fundamental Analysis", points=-5.0),
    ]


@pytest.mark.asyncio
async def test_run_panel_persists_one_opinion_per_agent_without_llm(session, stock, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "get_agent_panel_llm_adapter", lambda: None)
    snapshot = _snapshot(session, stock)
    decision = make_decision(symbol="2222", breakdown=_aligned_breakdown())

    await AgentPanelOrchestrator().run_panel(session, snapshot, decision, "2222")

    opinions = session.query(AgentOpinion).filter_by(snapshot_id=snapshot.id).all()
    names = {o.agent_name for o in opinions}
    assert names == {
        "Technical Analyst", "Fundamental Analyst", "Risk Manager", "Quant Analyst",
        "Macro Analyst", "News Analyst", "Sentiment Analyst",
    }
    assert all(o.used_llm is False for o in opinions)


@pytest.mark.asyncio
async def test_run_panel_does_not_create_a_debate_session_when_aligned(session, stock, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "get_agent_panel_llm_adapter", lambda: None)
    snapshot = _snapshot(session, stock)
    decision = make_decision(symbol="2222", breakdown=_aligned_breakdown())

    await AgentPanelOrchestrator().run_panel(session, snapshot, decision, "2222")

    assert session.query(DebateSession).count() == 0
    session.refresh(snapshot)
    assert snapshot.agent_debate_summary is None


@pytest.mark.asyncio
async def test_run_panel_creates_a_debate_session_when_conflicting(session, stock, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "get_agent_panel_llm_adapter", lambda: _FakeAdapter())
    snapshot = _snapshot(session, stock)
    decision = make_decision(symbol="2222", breakdown=_conflicting_breakdown())

    await AgentPanelOrchestrator().run_panel(session, snapshot, decision, "2222")

    debates = session.query(DebateSession).filter_by(snapshot_id=snapshot.id).all()
    assert len(debates) == 1
    assert debates[0].final_decision in ("BUY", "SELL", "HOLD")
    session.refresh(snapshot)
    assert snapshot.agent_debate_summary is not None
    assert "final_decision" in snapshot.agent_debate_summary


@pytest.mark.asyncio
async def test_run_panel_never_raises_even_when_a_step_fails(session, stock, monkeypatch):
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(orchestrator_module, "get_agent_panel_llm_adapter", _boom)
    snapshot = _snapshot(session, stock)
    decision = make_decision(symbol="2222", breakdown=_aligned_breakdown())

    # Must not raise.
    await AgentPanelOrchestrator().run_panel(session, snapshot, decision, "2222")

    assert session.query(AgentOpinion).filter_by(snapshot_id=snapshot.id).count() == 0
