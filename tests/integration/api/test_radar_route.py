"""Integration tests for the consumer-facing Smart Radar API
(/api/v1/radar/*) -- Basirah Radar V2 mandate Phase B/D (2026-08-17).

Covers: ordinary-user authorization (401/402/200), schema correctness
against a real RadarOpportunity + DecisionV2Snapshot pair, honest empty
states, dedup (superseded opportunities excluded), stale/fresh data
disclosure, and -- the mandate's hard safety requirement -- that these
routes spend zero SAHMK quota (never call the market data provider) on
a normal page render.

Uses conftest.py's plain `client`/`db_session` fixtures (not
`authenticated_as_staff`) for the auth-gating tests, since the whole
point there is to exercise the real, unoverridden get_current_user +
require_active_subscription dependency chain -- matching
test_market_data_subscription_gating.py's own convention. Read-only
data tests use `authenticated_as_staff` (an in-memory staff user
bypasses the subscription check) purely as a convenient "any entitled
caller" double, matching test_radar_v2_route.py's own convention.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import (
    DecisionV2Snapshot,
    RadarOpportunity,
    Stock,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    User,
)

_SUMMARY_ROUTE = "/api/v1/radar/summary"
_OPPORTUNITIES_ROUTE = "/api/v1/radar/opportunities"


def _detail_route(opportunity_id: int) -> str:
    return f"/api/v1/radar/opportunities/{opportunity_id}"


@pytest.fixture
def customer(db_session) -> User:
    user = User(email="customer@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def _as(user: User) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: user


def _make_stock(db_session, symbol="2222", name_ar="أرامكو السعودية", sector="الطاقة"):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", name_ar=name_ar, sector=sector)
    db_session.add(stock)
    db_session.commit()
    return stock


def _make_snapshot(
    db_session,
    stock,
    decision="BUY_CANDIDATE",
    decision_label_ar="شراء قوي",
    confidence=82.5,
    freshness="LIVE",
    scan_run_id=1,
):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        company_name_ar=stock.name_ar,
        sector_ar=stock.sector,
        decision=decision,
        decision_label_ar=decision_label_ar,
        confidence_score=Decimal(str(confidence)),
        opportunity_quality_score=Decimal("60"),
        risk_score=Decimal("40"),
        data_quality_score=Decimal("90"),
        data_freshness_status=freshness,
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
        scan_run_id=scan_run_id,
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


def _make_opportunity(
    db_session,
    stock,
    snapshot,
    stage1_rank=1,
    stage1_ranking_score=88.5,
    ranking_reason_ar="ارتفاع حجم التداول مع اختراق المقاومة",
    superseded_by_id=None,
    emitted_at=None,
):
    opportunity = RadarOpportunity(
        symbol=stock.symbol,
        stock_id=stock.id,
        decision_v2_snapshot_id=snapshot.id,
        scan_run_id=snapshot.scan_run_id,
        classification=snapshot.decision,
        classification_label_ar=snapshot.decision_label_ar,
        confidence_score=snapshot.confidence_score,
        price_at_signal=snapshot.current_price,
        stage1_rank=stage1_rank,
        stage1_ranking_score=Decimal(str(stage1_ranking_score)),
        stage1_component_scores={"trend": 80.0, "momentum": 75.0},
        stage1_signals=[{"name": "trending", "detail_ar": "اتجاه قوي"}],
        stage1_risk_reward_ratio=Decimal("1.8"),
        ranking_reason_ar=ranking_reason_ar,
        emitted_at=emitted_at or datetime.now(timezone.utc),
        superseded_by_id=superseded_by_id,
    )
    db_session.add(opportunity)
    db_session.commit()
    return opportunity


# --- authorization ----------------------------------------------------


@pytest.mark.parametrize("route", [_SUMMARY_ROUTE, _OPPORTUNITIES_ROUTE])
def test_anonymous_caller_is_rejected(client, route):
    response = client.get(route)
    assert response.status_code == 401


@pytest.mark.parametrize("route", [_SUMMARY_ROUTE, _OPPORTUNITIES_ROUTE])
def test_authenticated_caller_with_no_subscription_is_rejected(client, customer, route):
    _as(customer)
    response = client.get(route)
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "subscription_required"


@pytest.mark.parametrize("route", [_SUMMARY_ROUTE, _OPPORTUNITIES_ROUTE])
def test_a_real_trial_subscription_is_not_blocked(client, db_session, customer, route):
    future = datetime.now(timezone.utc) + timedelta(days=14)
    db_session.add(
        Subscription(
            user_id=customer.id,
            plan=SubscriptionPlan.TRIAL,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=future,
            current_period_start=datetime.now(timezone.utc),
            current_period_end=future,
        )
    )
    db_session.commit()

    _as(customer)
    response = client.get(route)
    assert response.status_code == 200


def test_opportunity_detail_requires_authentication(client):
    response = client.get(_detail_route(1))
    assert response.status_code == 401


def test_opportunity_detail_requires_active_subscription(client, customer):
    _as(customer)
    response = client.get(_detail_route(1))
    assert response.status_code == 402


# --- empty states -------------------------------------------------------


def test_summary_on_an_empty_database_is_an_honest_empty_state(client, db_session, authenticated_as_staff):
    response = client.get(_SUMMARY_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert body["live_opportunity_count"] == 0
    assert body["live_by_classification"] == {}
    assert body["average_confidence"] is None
    assert body["most_recent_emitted_at"] is None
    assert body["top_opportunities"] == []
    # Never a fabricated market read either -- a real enum value, but
    # never invented/guessed data alongside it.
    assert body["market_status"]
    assert body["market_risk_state"]


def test_opportunities_list_on_an_empty_database_is_an_empty_list(client, db_session, authenticated_as_staff):
    response = client.get(_OPPORTUNITIES_ROUTE)
    assert response.status_code == 200
    assert response.json() == []


def test_opportunity_detail_404s_for_a_missing_id(client, db_session, authenticated_as_staff):
    response = client.get(_detail_route(999999))
    assert response.status_code == 404


# --- schema correctness against a real opportunity -----------------------


def test_opportunities_list_reflects_a_real_live_opportunity(client, db_session, authenticated_as_staff):
    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock, freshness="LIVE")
    opportunity = _make_opportunity(db_session, stock, snapshot, stage1_rank=1)

    response = client.get(_OPPORTUNITIES_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["id"] == opportunity.id
    assert row["symbol"] == "2222"
    assert row["company_name_ar"] == "أرامكو السعودية"
    assert row["classification"] == "BUY_CANDIDATE"
    assert row["classification_label_ar"] == "شراء قوي"
    assert row["confidence_score"] == pytest.approx(82.5)
    assert row["stage1_rank"] == 1
    assert row["ranking_reason_ar"] == "ارتفاع حجم التداول مع اختراق المقاومة"
    assert row["data_freshness_status"] == "LIVE"
    assert row["entry_zone_low"] == pytest.approx(30.0)
    assert row["target_1"] == pytest.approx(32.0)
    assert row["stop_loss"] == pytest.approx(29.0)
    assert row["decision_v2_snapshot_id"] == snapshot.id


def test_opportunity_detail_includes_stage1_evidence_and_reasoning(client, db_session, authenticated_as_staff):
    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock)
    opportunity = _make_opportunity(db_session, stock, snapshot)

    response = client.get(_detail_route(opportunity.id))
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2222"
    assert body["stage1_component_scores"]["trend"] == pytest.approx(80.0)
    assert body["stage1_signals"] == [{"name": "trending", "detail_ar": "اتجاه قوي"}]
    assert body["stage1_risk_reward_ratio"] == pytest.approx(1.8)
    assert body["market_status"] == "OPEN"
    assert body["outcome_status"] is None  # no real outcome tracked yet -- not fabricated


def test_summary_reflects_a_real_live_opportunity(client, db_session, authenticated_as_staff):
    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock, confidence=90.0)
    _make_opportunity(db_session, stock, snapshot)

    response = client.get(_SUMMARY_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert body["live_opportunity_count"] == 1
    assert body["live_by_classification"] == {"BUY_CANDIDATE": 1}
    assert body["average_confidence"] == pytest.approx(90.0)
    assert len(body["top_opportunities"]) == 1
    assert body["top_opportunities"][0]["symbol"] == "2222"


def test_stale_data_freshness_is_disclosed_not_hidden(client, db_session, authenticated_as_staff):
    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock, freshness="STALE")
    _make_opportunity(db_session, stock, snapshot)

    response = client.get(_OPPORTUNITIES_ROUTE)
    assert response.status_code == 200
    assert response.json()[0]["data_freshness_status"] == "STALE"


def test_superseded_opportunities_are_excluded_from_list_and_summary(client, db_session, authenticated_as_staff):
    """Anti-flapping dedup (superseded_by_id) is a real structural
    guarantee -- a symbol that was re-emitted must appear once, as its
    newest live row, never alongside the stale one it replaced."""
    stock = _make_stock(db_session, "2222")
    old_snapshot = _make_snapshot(db_session, stock, confidence=60.0)
    old_opportunity = _make_opportunity(db_session, stock, old_snapshot, stage1_rank=3)

    new_snapshot = _make_snapshot(db_session, stock, confidence=85.0)
    new_opportunity = _make_opportunity(db_session, stock, new_snapshot, stage1_rank=1)

    old_opportunity.superseded_by_id = new_opportunity.id
    db_session.add(old_opportunity)
    db_session.commit()

    list_response = client.get(_OPPORTUNITIES_ROUTE)
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body) == 1
    assert body[0]["id"] == new_opportunity.id

    summary_response = client.get(_SUMMARY_ROUTE)
    assert summary_response.status_code == 200
    assert summary_response.json()["live_opportunity_count"] == 1


# --- zero SAHMK-provider-call guarantee -----------------------------------


def test_consumer_routes_never_call_the_market_data_provider(
    client, db_session, authenticated_as_staff, monkeypatch
):
    """The mandate's hard safety requirement: consumer radar reads must
    spend zero SAHMK quota. Proven directly by making the real provider
    factory raise if it is ever reached -- every route below must still
    return 200 without hitting that patched call."""
    from src.market_data import provider_factory

    async def _must_not_be_called(force_refresh=False):
        raise AssertionError("Consumer radar routes must never call get_market_data_provider().")

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _must_not_be_called)

    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock)
    opportunity = _make_opportunity(db_session, stock, snapshot)

    assert client.get(_SUMMARY_ROUTE).status_code == 200
    assert client.get(_OPPORTUNITIES_ROUTE).status_code == 200
    assert client.get(_detail_route(opportunity.id)).status_code == 200
