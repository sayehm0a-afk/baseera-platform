"""Integration tests for /api/v1/recommendations/history[/stats] -- the
public, real recommendation track record. Seeds RecommendationSnapshot/
RecommendationOutcome rows directly against in-memory SQLite and asserts
against real serialized output -- including the "never hides a failure"
and small-sample-warning guarantees the milestone explicitly requires.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.models import (
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    pass


def _seed_stock(session, symbol="2222"):
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _seed_snapshot(session, stock, symbol="2222", recommendation=RecommendationLabel.BUY, is_paper_trade=False):
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=symbol,
        evaluated_at=datetime.now(timezone.utc) - timedelta(days=10),
        market_price_at_evaluation=30.0,
        recommendation=recommendation,
        total_score=70.0,
        confidence_score=72.5,
        target_price=33.0,
        stop_loss=28.0,
        expected_return_pct=10.0,
        engine_version="2.0.0",
        is_paper_trade=is_paper_trade,
        reasons=["مؤشرات فنية إيجابية"],
        expires_at=datetime.now(timezone.utc) + timedelta(days=20),
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _seed_outcome(session, snapshot, horizon=7, status=RecommendationOutcomeStatus.PENDING, **kwargs):
    outcome = RecommendationOutcome(
        snapshot_id=snapshot.id,
        symbol=snapshot.symbol,
        evaluation_horizon_days=horizon,
        due_at=snapshot.evaluated_at + timedelta(days=horizon),
        status=status,
        **kwargs,
    )
    session.add(outcome)
    session.commit()
    return outcome


def test_history_requires_authentication(client, db_session):
    from src.api.dependencies import get_current_user
    import main

    main.app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/api/v1/recommendations/history")
    assert response.status_code in (401, 403)


def test_history_returns_seeded_snapshot_with_outcomes(client, db_session):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    _seed_outcome(db_session, snapshot, horizon=7, status=RecommendationOutcomeStatus.SUCCESSFUL, return_pct=5.2)

    response = client.get("/api/v1/recommendations/history")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["symbol"] == "2222"
    assert item["company_name_ar"] == "أرامكو السعودية"
    assert item["recommendation"] == "BUY"
    assert len(item["outcomes"]) == 1
    assert item["outcomes"][0]["status"] == "SUCCESSFUL"
    assert item["outcomes"][0]["return_pct"] == 5.2


def test_history_never_hides_a_failed_outcome(client, db_session):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    _seed_outcome(db_session, snapshot, horizon=7, status=RecommendationOutcomeStatus.FAILED, return_pct=-8.0)

    response = client.get("/api/v1/recommendations/history")
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["outcomes"][0]["status"] == "FAILED"


def test_history_excludes_paper_trades(client, db_session):
    stock = _seed_stock(db_session)
    _seed_snapshot(db_session, stock, is_paper_trade=True)

    response = client.get("/api/v1/recommendations/history")
    assert response.json()["total"] == 0


def test_history_filters_by_symbol(client, db_session):
    stock_a = _seed_stock(db_session, "2222")
    stock_b = _seed_stock(db_session, "1120")
    _seed_snapshot(db_session, stock_a, "2222")
    _seed_snapshot(db_session, stock_b, "1120")

    response = client.get("/api/v1/recommendations/history", params={"symbol": "1120"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "1120"


def test_history_filters_by_overall_status(client, db_session):
    stock = _seed_stock(db_session)
    snapshot = _seed_snapshot(db_session, stock)
    _seed_outcome(db_session, snapshot, horizon=7, status=RecommendationOutcomeStatus.SUCCESSFUL)

    response = client.get("/api/v1/recommendations/history", params={"status": "COMPLETED"})
    assert response.json()["total"] == 1

    response = client.get("/api/v1/recommendations/history", params={"status": "ACTIVE"})
    assert response.json()["total"] == 0


def test_history_item_with_no_outcomes_reports_not_yet_tracked(client, db_session):
    stock = _seed_stock(db_session)
    _seed_snapshot(db_session, stock)

    response = client.get("/api/v1/recommendations/history")
    body = response.json()
    assert body["items"][0]["overall_status"] == "NO_OUTCOMES_TRACKED"
    assert body["items"][0]["outcomes"] == []


def test_stats_reports_real_win_rate_and_sample_size(client, db_session):
    stock = _seed_stock(db_session)
    for i in range(3):
        snapshot = _seed_snapshot(db_session, stock, symbol="2222")
        status = RecommendationOutcomeStatus.SUCCESSFUL if i < 2 else RecommendationOutcomeStatus.FAILED
        _seed_outcome(
            db_session, snapshot, horizon=7, status=status, return_pct=5.0 if status.value == "SUCCESSFUL" else -3.0,
            hit_target=(status == RecommendationOutcomeStatus.SUCCESSFUL), hit_stop=(status == RecommendationOutcomeStatus.FAILED),
        )

    response = client.get("/api/v1/recommendations/history/stats", params={"evaluation_horizon_days": 7})
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_horizon_days"] == 7
    assert body["sample_size"] == 3
    assert body["terminal_sample_size"] == 3
    assert body["win_rate"] == pytest.approx(66.67, abs=0.01)
    assert body["small_sample_warning"] is True


def test_stats_with_zero_samples_returns_null_metrics_not_fabricated_zero(client, db_session):
    response = client.get("/api/v1/recommendations/history/stats", params={"evaluation_horizon_days": 7})
    assert response.status_code == 200
    body = response.json()
    assert body["sample_size"] == 0
    assert body["win_rate"] is None
    assert body["small_sample_warning"] is True


def test_stats_falls_back_to_7_days_for_an_unsupported_horizon(client, db_session):
    response = client.get("/api/v1/recommendations/history/stats", params={"evaluation_horizon_days": 5})
    assert response.status_code == 200
    assert response.json()["evaluation_horizon_days"] == 7
