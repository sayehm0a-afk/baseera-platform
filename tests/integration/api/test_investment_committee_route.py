"""Integration tests for the AI Multi-Agent Investment Committee's
wiring into GET /api/v1/stocks/{symbol}/decision-v2 -- real FastAPI
routing, real committee orchestration, against an in-memory SQLite DB
(see conftest.py). Reuses test_decision_v2_route.py's own stock/bar/
fundamental fixtures rather than duplicating them.
"""

import pytest
from sqlalchemy.orm import Session

from src.domain.models import CommitteeAgentOpinion, CommitteeConsensus, DecisionV2Snapshot
from tests.integration.api.test_decision_v2_route import _add_bars, _add_fundamentals, _make_stock


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    """Every /api/v1/stocks/* route requires require_active_subscription()."""


def test_committee_runs_and_is_present_in_response(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert body["committee"] is not None
    committee = body["committee"]
    assert committee["final_decision"] in ("BUY", "SELL", "HOLD")
    assert 0.0 <= committee["final_confidence"] <= 100.0
    assert committee["participant_count"] == 8
    assert 0.0 <= committee["agreement_pct"] <= 100.0
    assert 0.0 <= committee["disagreement_pct"] <= 100.0
    assert committee["agreement_pct"] + committee["disagreement_pct"] == pytest.approx(100.0)
    assert committee["consensus_reasoning_ar"]
    assert len(committee["opinions"]) == 8

    expected_roles = {
        "technical", "fundamental", "news", "market_sentiment", "risk",
        "liquidity_volume", "macro", "portfolio_allocation",
    }
    assert {op["role"] for op in committee["opinions"]} == expected_roles
    for opinion in committee["opinions"]:
        assert opinion["stance"] in ("BULLISH", "BEARISH", "NEUTRAL", "UNAVAILABLE")
        assert isinstance(opinion["evidence"], list)
        assert isinstance(opinion["rejection_reasons"], list)

    # Macro is always a disclosed no-op (no real macro data source).
    macro = next(op for op in committee["opinions"] if op["role"] == "macro")
    assert macro["stance"] == "UNAVAILABLE"


def test_committee_opinions_and_consensus_are_persisted(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200

    snapshot = db_session.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.symbol == "2222").one()

    opinions = db_session.query(CommitteeAgentOpinion).filter(
        CommitteeAgentOpinion.decision_v2_snapshot_id == snapshot.id
    ).all()
    assert len(opinions) == 8
    for opinion in opinions:
        assert opinion.agent_name
        assert opinion.reasoning

    consensus_rows = db_session.query(CommitteeConsensus).filter(
        CommitteeConsensus.decision_v2_snapshot_id == snapshot.id
    ).all()
    assert len(consensus_rows) == 1
    consensus_row = consensus_rows[0]
    assert consensus_row.final_decision in ("BUY", "SELL", "HOLD")
    assert consensus_row.consensus_reasoning_ar
    assert isinstance(consensus_row.weighted_votes, dict)


def test_committee_absent_when_snapshot_persistence_fails(client, db_session, monkeypatch):
    """The committee's FK depends on a persisted DecisionV2Snapshot --
    when that insert fails (best-effort, same discipline as the
    snapshot itself), the committee must not run at all rather than
    fail with an orphan FK or a half-run partial result."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    original_add = Session.add
    calls = {"n": 0}

    def _failing_add(self, obj, *args, **kwargs):
        if type(obj).__name__ == "DecisionV2Snapshot":
            calls["n"] += 1
            raise RuntimeError("simulated persistence failure")
        return original_add(self, obj, *args, **kwargs)

    monkeypatch.setattr(Session, "add", _failing_add)

    resp = client.get("/api/v1/stocks/2222/decision-v2")
    assert resp.status_code == 200
    assert resp.json()["committee"] is None
    assert calls["n"] == 1
