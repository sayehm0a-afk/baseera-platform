"""Regression test for InvestmentCommitteeOrchestrator's persistence
step -- real SQLAlchemy ORM against an in-memory SQLite DB, no mocking
of the persistence layer itself (same technique as
tests/unit/market_intelligence/repositories/test_market_intelligence_repository.py).
"""

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.committee import agents as committee_agents
from src.ai_evolution.committee.orchestrator import InvestmentCommitteeOrchestrator
from src.ai_evolution.committee.types import AgentVerdict
from src.core.db.database import Base
from src.domain.models import AgentStance
from tests.unit.ai_evolution.committee._fixtures import make_decision_result, make_investment_decision


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_run_committee_coerces_numpy_confidence_before_it_reaches_the_orm(session, monkeypatch):
    """Regression for a real production failure (2026-09-13): the
    Portfolio Allocation Agent derives its confidence from
    `result.risk_reward_target_1` (`min(100.0, risk_reward * 30.0)`),
    which is `numpy.float64` whenever that ratio comes from
    DecisionEngineV2's numpy-backed computations -- Python's built-in
    `min()` does not coerce, so the numpy type survives into
    `AgentVerdict.confidence`. SQLAlchemy 2.0's insertmanyvalues
    RETURNING path literal-renders Numeric parameters, and numpy's
    `repr()` (`np.float64(56.7)`) is not valid SQL -- confirmed live as
    'psycopg2.errors.InvalidSchemaName: schema "np" does not exist',
    which silently dropped the entire committee breakdown for a live
    symbol (the whole `run_committee` call is wrapped in a bare
    except, see its own docstring). SQLite (this test's DB) tolerates
    the un-coerced type silently and a post-commit read-back can't
    distinguish a fixed call from a broken one, so this test captures
    the exact object `session.add()` receives (via a spy) and checks
    *its* attribute types, matching the technique already established
    in test_market_intelligence_repository.py for the same bug class.
    """
    monkeypatch.setattr(
        committee_agents,
        "analyze_news",
        lambda session, symbol, news_events: _fake_news_verdict(),
    )

    investment_decision = make_investment_decision()
    result = make_decision_result(risk_reward_target_1=np.float64(2.5))

    captured_opinions = []
    captured_consensus = []
    original_add = session.add

    def _spy_add(obj):
        if type(obj).__name__ == "CommitteeAgentOpinion":
            captured_opinions.append(type(obj.confidence))
        elif type(obj).__name__ == "CommitteeConsensus":
            captured_consensus.append(
                {
                    f: type(getattr(obj, f))
                    for f in ("final_confidence", "agreement_pct", "disagreement_pct", "disagreement_score")
                }
            )
        return original_add(obj)

    monkeypatch.setattr(session, "add", _spy_add)

    orchestrator = InvestmentCommitteeOrchestrator()
    consensus = await orchestrator.run_committee(
        session, decision_v2_snapshot_id=1, symbol="2222",
        investment_decision=investment_decision, result=result, news_events=[],
    )

    assert consensus is not None, "run_committee swallowed an exception -- the exact failure mode this guards against"
    assert len(captured_opinions) == 8
    for field_type in captured_opinions:
        assert field_type is float, f"CommitteeAgentOpinion.confidence was {field_type!r}, expected plain float"

    assert len(captured_consensus) == 1
    for field, field_type in captured_consensus[0].items():
        assert field_type is float, f"CommitteeConsensus.{field} was {field_type!r}, expected plain float"


async def _fake_news_verdict() -> AgentVerdict:
    return AgentVerdict(
        agent_name="News Intelligence Agent", role="news", stance=AgentStance.UNAVAILABLE,
        confidence=0.0, reasoning="لا تتوفر أخبار محللة ذات صلة.", evidence=[], rejection_reasons=[],
    )
