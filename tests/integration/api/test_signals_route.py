"""Integration tests for POST/GET/DELETE /api/v1/signals -- "متابعة
هذه الإشارة" (follow this signal) and the personal-vs-algorithm
performance comparison (product decision 2026-09-18).

Reuses the same as_user/other_user/_make_stock/_add_decision_v2
pattern already established by test_watchlist_route.py.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    Stock,
    User,
    UserFollowedSignal,
)


@pytest.fixture
def as_user(db_session):
    user = User(email="user@example.com", password_hash="hashed", is_staff=False)
    db_session.add(user)
    db_session.commit()
    main.app.dependency_overrides[get_current_user] = lambda: user
    yield user


@pytest.fixture
def other_user(db_session):
    user = User(email="other@example.com", password_hash="hashed", is_staff=False)
    db_session.add(user)
    db_session.commit()
    return user


def _make_stock(db_session, symbol="2222", name_ar="أرامكو السعودية", sector="الطاقة"):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", name_ar=name_ar, sector=sector)
    db_session.add(stock)
    db_session.commit()
    return stock


def _add_decision_v2(db_session, symbol, decision="BUY_CANDIDATE", confidence=75.0):
    stock = db_session.query(Stock).filter(Stock.symbol == symbol).one()
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=symbol,
        company_name_en=f"Stock {symbol}",
        company_name_ar=stock.name_ar,
        sector_ar=stock.sector,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=Decimal(str(confidence)),
        opportunity_quality_score=Decimal("60"),
        risk_score=Decimal("40"),
        data_quality_score=Decimal("90"),
        data_freshness_status="LIVE",
        current_price=Decimal("30.5"),
        entry_zone_low=Decimal("30.0"),
        entry_zone_high=Decimal("30.6"),
        stop_loss=Decimal("29.0"),
        target_1=Decimal("32.0"),
        target_2=Decimal("33.0"),
        target_3=Decimal("34.0"),
        market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0",
        data_source="SAHMK_REAL",
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


def _add_outcome(db_session, snapshot, status):
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        symbol=snapshot.symbol,
        due_at=datetime.now(timezone.utc) + timedelta(days=7),
        status=status,
        return_pct=Decimal("4.9") if status == DecisionV2OutcomeStatus.TARGET_1_HIT else None,
    )
    db_session.add(outcome)
    db_session.commit()
    return outcome


# --- authentication ---------------------------------------------------


def test_follow_requires_authentication(client, db_session):
    response = client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": 1})
    assert response.status_code == 401


def test_get_followed_requires_authentication(client, db_session):
    response = client.get("/api/v1/signals/followed")
    assert response.status_code == 401


def test_get_performance_requires_authentication(client, db_session):
    response = client.get("/api/v1/signals/performance")
    assert response.status_code == 401


# --- POST /follow -------------------------------------------------------


def test_follow_succeeds_for_an_actionable_buy_decision(client, db_session, as_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222", decision="STRONG_BUY_CANDIDATE")

    response = client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": snapshot.id})

    assert response.status_code == 201
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["decision"] == "STRONG_BUY_CANDIDATE"
    assert body["target_1"] == pytest.approx(32.0)
    assert body["outcome_status"] is None  # no DecisionV2Outcome yet -- must not be fabricated

    rows = db_session.query(UserFollowedSignal).filter_by(user_id=as_user.id).all()
    assert len(rows) == 1
    assert rows[0].decision_v2_snapshot_id == snapshot.id


def test_follow_rejects_a_non_actionable_decision(client, db_session, as_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222", decision="WATCH")

    response = client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": snapshot.id})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "signal_not_actionable"


def test_follow_rejects_an_unknown_snapshot(client, db_session, as_user):
    response = client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": 999})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "signal_snapshot_not_found"


def test_follow_rejects_a_duplicate(client, db_session, as_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222")
    client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": snapshot.id})

    response = client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": snapshot.id})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "signal_already_followed"


def test_follow_includes_the_real_outcome_once_one_exists(client, db_session, as_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222")
    _add_outcome(db_session, snapshot, DecisionV2OutcomeStatus.TARGET_1_HIT)

    response = client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": snapshot.id})

    assert response.status_code == 201
    body = response.json()
    assert body["outcome_status"] == "TARGET_1_HIT"
    assert body["outcome_status_label_ar"] == "تحقق الهدف الأول"
    assert body["outcome_return_pct"] == pytest.approx(4.9)


# --- DELETE /{id} ---------------------------------------------------------


def test_unfollow_succeeds(client, db_session, as_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222")
    client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": snapshot.id})

    response = client.delete(f"/api/v1/signals/{snapshot.id}")

    assert response.status_code == 200
    assert db_session.query(UserFollowedSignal).filter_by(user_id=as_user.id).all() == []


def test_unfollow_404_when_not_followed(client, db_session, as_user):
    response = client.delete("/api/v1/signals/999")
    assert response.status_code == 404


# --- GET /followed ---------------------------------------------------------


def test_get_followed_is_empty_for_a_new_user(client, db_session, as_user):
    response = client.get("/api/v1/signals/followed")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_user_cannot_see_another_users_followed_signals(client, db_session, as_user, other_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222")
    db_session.add(UserFollowedSignal(user_id=other_user.id, decision_v2_snapshot_id=snapshot.id, symbol="2222"))
    db_session.commit()

    response = client.get("/api/v1/signals/followed")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_user_cannot_unfollow_another_users_signal(client, db_session, as_user, other_user):
    _make_stock(db_session, "2222")
    snapshot = _add_decision_v2(db_session, "2222")
    db_session.add(UserFollowedSignal(user_id=other_user.id, decision_v2_snapshot_id=snapshot.id, symbol="2222"))
    db_session.commit()

    response = client.delete(f"/api/v1/signals/{snapshot.id}")

    assert response.status_code == 404
    remaining = db_session.query(UserFollowedSignal).filter_by(user_id=other_user.id).all()
    assert len(remaining) == 1


# --- GET /performance -------------------------------------------------------


def test_performance_is_honest_about_no_data(client, db_session, as_user):
    response = client.get("/api/v1/signals/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["personal_resolved_sample_size"] == 0
    assert body["personal_win_rate_pct"] is None
    assert body["algorithm_resolved_sample_size"] == 0
    assert body["algorithm_win_rate_pct"] is None
    assert body["insufficient_data_message_ar"] is not None


def test_performance_counts_only_the_users_own_followed_resolved_outcomes(client, db_session, as_user):
    _make_stock(db_session, "2222")
    followed_win = _add_decision_v2(db_session, "2222")
    _add_outcome(db_session, followed_win, DecisionV2OutcomeStatus.TARGET_1_HIT)
    client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": followed_win.id})

    # Not followed by this user -- must count toward the algorithm's
    # aggregate but never toward this user's own personal win rate.
    not_followed_loss = _add_decision_v2(db_session, "2222")
    _add_outcome(db_session, not_followed_loss, DecisionV2OutcomeStatus.STOP_LOSS_HIT)

    response = client.get("/api/v1/signals/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["personal_resolved_sample_size"] == 1
    assert body["personal_win_rate_pct"] == pytest.approx(100.0)
    assert body["algorithm_resolved_sample_size"] == 2
    assert body["algorithm_win_rate_pct"] == pytest.approx(50.0)
    assert body["personal_small_sample_warning"] is True  # 1 < MIN_RESOLVED_SAMPLE_SIZE


def test_performance_excludes_pending_and_partial_outcomes_from_win_rate(client, db_session, as_user):
    _make_stock(db_session, "2222")
    pending = _add_decision_v2(db_session, "2222")
    _add_outcome(db_session, pending, DecisionV2OutcomeStatus.PENDING)
    client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": pending.id})

    partial = _add_decision_v2(db_session, "2222")
    _add_outcome(db_session, partial, DecisionV2OutcomeStatus.PARTIAL)
    client.post("/api/v1/signals/follow", json={"decision_v2_snapshot_id": partial.id})

    response = client.get("/api/v1/signals/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["personal_resolved_sample_size"] == 0
    assert body["personal_win_rate_pct"] is None
