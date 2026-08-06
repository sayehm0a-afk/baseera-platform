"""Integration tests for /api/v1/admin/investment-committee/* -- real
FastAPI routing against in-memory SQLite, seeding `DecisionV2Snapshot`/
`CommitteeConsensus`/`CommitteeAgentOpinion` rows directly (the
committee orchestration itself is already covered end-to-end by
test_investment_committee_route.py) so these tests focus on the admin
query/serialization layer.
"""

from datetime import datetime, timezone

import pytest

from src.domain.models import AgentStance, CommitteeAgentOpinion, CommitteeConsensus, DecisionV2Snapshot, Stock


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    pass


def _seed_stock(session, symbol="2222"):
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _seed_snapshot(session, stock, symbol="2222"):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id, symbol=symbol, company_name_ar="أرامكو السعودية", company_name_en="Saudi Aramco",
        sector_ar="الطاقة", decision="BUY_CANDIDATE", decision_label_ar="مرشح شراء",
        confidence_score=65.0, opportunity_quality_score=60.0, risk_score=35.0, data_quality_score=100.0,
        data_freshness_status="LIVE", market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0", data_source="SAHMK_REAL",
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _seed_committee(session, snapshot):
    session.add(
        CommitteeAgentOpinion(
            decision_v2_snapshot_id=snapshot.id, agent_name="Technical Analysis Agent", agent_role="technical",
            stance=AgentStance.BULLISH, confidence=80.0, reasoning="اتجاه صاعد", evidence=["نقطة 1"],
            rejection_reasons=[], used_llm=False,
        )
    )
    session.add(
        CommitteeAgentOpinion(
            decision_v2_snapshot_id=snapshot.id, agent_name="Macro Economy Agent", agent_role="macro",
            stance=AgentStance.UNAVAILABLE, confidence=0.0, reasoning="لا تتوفر بيانات كلية",
            evidence=[], rejection_reasons=["لا يوجد مصدر بيانات كلية حقيقي"], used_llm=False,
        )
    )
    consensus = CommitteeConsensus(
        decision_v2_snapshot_id=snapshot.id, final_decision="BUY", final_confidence=72.5,
        participant_count=8, directional_count=1, agreement_pct=100.0, disagreement_pct=0.0,
        disagreement_score=0.0, most_optimistic_agent="Technical Analysis Agent",
        most_optimistic_stance="BULLISH", most_conservative_agent="Macro Economy Agent",
        most_conservative_stance="UNAVAILABLE",
        consensus_reasoning_ar="توصلت اللجنة إلى توافق حول الشراء.",
        rejected_alternatives=[], weighted_votes={"Technical Analysis Agent": 0.96, "Macro Economy Agent": 0.0},
    )
    session.add(consensus)
    session.commit()
    return consensus


def test_list_sessions_returns_seeded_session(client, db_session):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    _seed_committee(db_session, snapshot)

    response = client.get("/api/v1/admin/investment-committee/sessions")
    assert response.status_code == 200
    body = response.json()
    assert body["total_sessions"] == 1
    row = body["sessions"][0]
    assert row["symbol"] == "2222"
    assert row["final_decision"] == "BUY"
    assert row["agreement_pct"] == 100.0
    assert row["most_optimistic_agent"] == "Technical Analysis Agent"


def test_list_sessions_filters_by_symbol(client, db_session):
    stock_a = _seed_stock(db_session, "2222")
    stock_b = _seed_stock(db_session, "1120")
    _seed_committee(db_session, _seed_snapshot(db_session, stock_a, "2222"))
    _seed_committee(db_session, _seed_snapshot(db_session, stock_b, "1120"))

    response = client.get("/api/v1/admin/investment-committee/sessions", params={"symbol": "1120"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_sessions"] == 1
    assert body["sessions"][0]["symbol"] == "1120"


def test_get_session_detail_includes_agent_opinions(client, db_session):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    consensus = _seed_committee(db_session, snapshot)

    response = client.get(f"/api/v1/admin/investment-committee/sessions/{consensus.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["final_decision"] == "BUY"
    assert len(body["opinions"]) == 2
    roles = {op["role"] for op in body["opinions"]}
    assert roles == {"technical", "macro"}
    macro_opinion = next(op for op in body["opinions"] if op["role"] == "macro")
    assert macro_opinion["stance"] == "UNAVAILABLE"
    assert macro_opinion["rejection_reasons"]


def test_get_session_detail_404_for_unknown_id(client, db_session):
    response = client.get("/api/v1/admin/investment-committee/sessions/999999")
    assert response.status_code == 404


def test_stats_aggregates_real_sessions(client, db_session):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    _seed_committee(db_session, snapshot)

    response = client.get("/api/v1/admin/investment-committee/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_sessions"] == 1
    assert body["average_agreement_pct"] == 100.0
    assert body["final_decision_distribution"] == {"BUY": 1}
    assert body["most_optimistic_agent_counts"] == {"Technical Analysis Agent": 1}


def test_stats_empty_window_returns_zero_sessions(client, db_session):
    response = client.get("/api/v1/admin/investment-committee/stats", params={"within_hours": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total_sessions"] == 0
    assert body["average_agreement_pct"] is None
