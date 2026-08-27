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
    MarketScanRun,
    MarketScanStatus,
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


def test_summary_market_risk_never_selects_a_newer_shadow_run(client, db_session, authenticated_as_staff, monkeypatch):
    """PR #105 independent audit: radar.py's _latest_market_breadth()
    (module docstring: "identical convention to
    src.api.routes.stocks._latest_market_breadth") shares the same
    repository call site market.py's leak used. A newer, Shadow-
    internal MarketScanRun with a deliberately different breadth
    signature (would classify as DEFENSIVE_EXIT-biased) must never be
    selected over the real, older consumer scan (STRONG_ENTRY-biased)."""
    from src.market_intelligence.market_status import MarketSessionStatus, MarketStatusInfo
    from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
    from src.analysis.recommendation.types import Recommendation
    from tests.unit.market_intelligence._fixtures import make_decision, make_outcome

    def _open_status():
        return MarketStatusInfo(
            status=MarketSessionStatus.OPEN, label_ar="السوق مفتوح", is_trading_day=True,
            server_time_riyadh=datetime(2026, 1, 4, 12, 0, tzinfo=timezone.utc),
            seconds_until_next_open=0.0, seconds_until_close=3600.0, last_completed_session_date=None,
        )

    monkeypatch.setattr("src.api.routes.radar.get_market_status", _open_status)

    async def _seed_breadth(prefix, buy_count, sell_count):
        repo = MarketIntelligenceRepository()
        total = buy_count + sell_count
        symbols = [f"{prefix}{i:02d}" for i in range(total)]
        for symbol in symbols:
            db_session.add(Stock(symbol=symbol, name_en=f"Stock {symbol}"))
        db_session.commit()
        run = repo.create_scan_run(db_session, symbols_requested=total)
        outcomes = [
            make_outcome(symbol=s, decision=make_decision(symbol=s, recommendation=Recommendation.BUY, confidence=80.0))
            for s in symbols[:buy_count]
        ] + [
            make_outcome(symbol=s, decision=make_decision(symbol=s, recommendation=Recommendation.SELL, confidence=80.0))
            for s in symbols[buy_count:]
        ]
        await repo.save_symbol_records(db_session, run.id, outcomes)
        repo.finish_run(db_session, run.id, MarketScanStatus.SUCCESS, symbols_succeeded=total, symbols_skipped=0, symbols_failed=0)
        return repo.get_run(db_session, run.id)

    import asyncio

    consumer_run = asyncio.run(_seed_breadth("92", 18, 2))  # STRONG_ENTRY-biased
    shadow_run = asyncio.run(_seed_breadth("93", 1, 19))  # DEFENSIVE_EXIT-biased
    assert shadow_run.id > consumer_run.id

    from src.domain.models import RecurrentScanCycle, RecurrentScanCycleStatus

    db_session.add(RecurrentScanCycle(
        cycle_id="audit-radar-shadow-cycle", status=RecurrentScanCycleStatus.SUCCESS_NO_CHANGE,
        scan_run_id=shadow_run.id, triggered_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    real_response = client.get(_SUMMARY_ROUTE)
    assert real_response.status_code == 200
    real_state = real_response.json()["market_risk_state"]
    assert real_state not in ("MARKET_CLOSED", "INSUFFICIENT_DATA")

    # If Shadow leaked in, this exact scenario would classify
    # DEFENSIVE_EXIT (entries blocked) -- must not happen.
    assert real_response.json()["entry_permitted"] is True
    assert real_state != "DEFENSIVE_EXIT"


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
    # No Radar V2 cycle has ever completed -- the real scan funnel is
    # honestly absent, never a fabricated 0.
    assert body["stage1_universe_size"] is None
    assert body["stage1_evaluated_count"] is None
    assert body["stage1_candidate_count"] is None
    assert body["stage2_validated_count"] is None
    assert body["final_opportunities_count"] is None
    assert body["last_full_scan_at"] is None
    # The live-validation cap itself is a config constant, always
    # available regardless of whether any cycle has run yet.
    assert body["stage2_candidate_cap"] == 15


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


def test_opportunities_list_exposes_calibrated_confidence_when_the_snapshot_has_one(
    client, db_session, authenticated_as_staff
):
    """RADAR-C/VAL-8: the linked DecisionV2Snapshot's calibrated
    confidence companion figure must reach the radar API alongside the
    raw score, not be silently dropped -- confidence_score stays the
    raw value regardless."""
    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock, confidence=82.5)
    snapshot.calibrated_confidence_score = Decimal("77.3")
    snapshot.calibration_version = "decision_v2-v3"
    db_session.add(snapshot)
    db_session.commit()
    _make_opportunity(db_session, stock, snapshot)

    response = client.get(_OPPORTUNITIES_ROUTE)
    assert response.status_code == 200
    row = response.json()[0]
    assert row["confidence_score"] == pytest.approx(82.5)
    assert row["calibrated_confidence_score"] == pytest.approx(77.3)
    assert row["calibration_version"] == "decision_v2-v3"


def test_opportunities_list_calibrated_confidence_is_honestly_none_without_an_active_model(
    client, db_session, authenticated_as_staff
):
    """No active confidence_calibration_models row for the decision_v2
    source -- the companion field must be null, never fabricated or
    defaulted to the raw score."""
    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock)
    _make_opportunity(db_session, stock, snapshot)

    response = client.get(_OPPORTUNITIES_ROUTE)
    assert response.status_code == 200
    row = response.json()[0]
    assert row["calibrated_confidence_score"] is None
    assert row["calibration_version"] is None


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


def test_summary_excludes_a_stale_decision_from_live_count_and_preview(client, db_session, authenticated_as_staff):
    """Production truthfulness fix (2026-08-23) regression fixture: a
    real production case, symbol 6060, was emitted 3 days ago (STALE)
    yet still rendered as an actionable "شراء" inside "الفرص الحية"
    because only `entry_status` (not `is_decision_fresh`) gated
    membership. A stale RadarOpportunity must not count toward
    live_opportunity_count, average_confidence, live_by_classification,
    or occupy a top_opportunities preview slot -- Decision V2
    classification/scoring/ranking are untouched, this is membership
    truthfulness only."""
    stale_stock = _make_stock(db_session, "6060", name_ar="الشرقية للتنمية")
    stale_snapshot = _make_snapshot(db_session, stale_stock, confidence=60.0)
    _make_opportunity(
        db_session, stale_stock, stale_snapshot,
        emitted_at=datetime.now(timezone.utc) - timedelta(days=5),
    )

    fresh_stock = _make_stock(db_session, "2222")
    fresh_snapshot = _make_snapshot(db_session, fresh_stock, confidence=90.0)
    _make_opportunity(db_session, fresh_stock, fresh_snapshot)

    response = client.get(_SUMMARY_ROUTE)
    assert response.status_code == 200
    body = response.json()

    assert body["live_opportunity_count"] == 1
    assert body["average_confidence"] == pytest.approx(90.0)
    symbols_in_preview = [o["symbol"] for o in body["top_opportunities"]]
    assert "6060" not in symbols_in_preview
    assert "2222" in symbols_in_preview


def test_summary_reports_the_real_stage1_scan_funnel_from_the_latest_radar_v2_run(
    client, db_session, authenticated_as_staff
):
    """The exact gap this test guards: before this fix, a consumer only
    ever saw the capped live-opportunity count (e.g. 15) with no way to
    tell that Stage 1 had actually scanned the full local universe for
    free -- reading as "the radar only checked 15 stocks." Once a Radar
    V2 cycle has persisted its Stage 1 metrics, /summary must surface
    them honestly."""
    older_run = MarketScanRun(
        status=MarketScanStatus.SUCCESS, symbols_requested=10,
        stage1_universe_size=200, stage1_evaluated_count=198, stage1_candidate_count=40,
    )
    db_session.add(older_run)
    db_session.commit()

    newer_run = MarketScanRun(
        status=MarketScanStatus.SUCCESS, symbols_requested=15, symbols_succeeded=13,
        stage1_universe_size=231, stage1_evaluated_count=228, stage1_candidate_count=52,
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(newer_run)
    db_session.commit()

    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock, scan_run_id=newer_run.id)
    _make_opportunity(db_session, stock, snapshot)

    response = client.get(_SUMMARY_ROUTE)
    assert response.status_code == 200
    body = response.json()
    # The latest run's numbers win, not the first one found.
    assert body["stage1_universe_size"] == 231
    assert body["stage1_evaluated_count"] == 228
    assert body["stage1_candidate_count"] == 52
    assert body["stage2_candidate_cap"] == 15
    assert body["stage2_validated_count"] == 13
    assert body["final_opportunities_count"] == 1
    assert body["last_full_scan_at"] is not None


def test_summary_ignores_an_ordinary_market_scan_run_with_no_stage1_metrics(
    client, db_session, authenticated_as_staff
):
    """A MarketScanRun created by an ordinary (non-Radar-V2) market
    scan never gets stage1_universe_size/candidate_count populated --
    it must never be mistaken for real Radar V2 funnel data."""
    ordinary_run = MarketScanRun(status=MarketScanStatus.SUCCESS, symbols_requested=50)
    db_session.add(ordinary_run)
    db_session.commit()

    response = client.get(_SUMMARY_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert body["stage1_universe_size"] is None
    assert body["stage1_candidate_count"] is None


def test_summary_funnel_is_honestly_null_for_a_real_radar_v2_run_that_predates_the_fix(
    client, db_session, authenticated_as_staff
):
    """Reproduces the exact production failure mode found during the
    BASIRAH Final Pre-Live Fix investigation (2026-08-19): a real Radar
    V2 cycle ran and emitted real, live RadarOpportunity rows (proving
    the pipeline executed end-to-end), but that specific MarketScanRun
    row predates the stage1-funnel-persistence deploy (PR #75) and so
    never had record_stage1_metrics called against it --
    stage1_universe_size/evaluated_count/candidate_count/last_full_scan_at
    stay genuinely None on that row forever, by design (a plain UPDATE
    is never backfilled retroactively). /summary must keep reporting
    the real live opportunities while being honest that the funnel
    breakdown for that historical run was never recorded -- never
    fabricating a number, and never crashing because
    get_latest_run_with_stage1_metrics() correctly finds no matching row."""
    pre_fix_run = MarketScanRun(
        status=MarketScanStatus.SUCCESS,
        symbols_requested=15,
        symbols_succeeded=15,
        symbols_failed=0,
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(pre_fix_run)
    db_session.commit()

    stock = _make_stock(db_session, "2222")
    snapshot = _make_snapshot(db_session, stock, scan_run_id=pre_fix_run.id)
    _make_opportunity(db_session, stock, snapshot)

    response = client.get(_SUMMARY_ROUTE)
    assert response.status_code == 200
    body = response.json()

    # The real opportunity is still reported honestly.
    assert body["live_opportunity_count"] == 1

    # The funnel is honestly null for this run, not fabricated as 0 or
    # silently matching some other run's numbers.
    assert body["stage1_universe_size"] is None
    assert body["stage1_evaluated_count"] is None
    assert body["stage1_candidate_count"] is None
    assert body["stage2_validated_count"] is None
    assert body["final_opportunities_count"] is None
    assert body["last_full_scan_at"] is None
    # The cap itself is a static config value, always reported.
    assert body["stage2_candidate_cap"] == 15


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
