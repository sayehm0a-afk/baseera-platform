"""Integration tests for the Basirah Radar V2 REST API
(/api/v1/admin/market-intelligence/radar-v2/*). Mirrors the fixtures
and fakes test_admin_market_intelligence_route.py already established
for /continue-scan-cycle -- Radar V2's POST .../radar-v2/scan reuses
the identical _run_one_bounded_background_cycle safety machinery, so
the same leader-lock/SAHMK-health doubles apply here.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user, get_market_provider
from src.core.db import database
from src.core.db.database import Base, get_db
from src.domain.models import PriceBar, StaffRole, Stock, Timeframe, User
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_market_provider] = lambda: DevMarketDataProvider()
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


@pytest.fixture
def as_staff():
    staff_user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    main.app.dependency_overrides[get_current_user] = lambda: staff_user
    yield staff_user


@pytest.fixture
def as_analyst():
    analyst = User(email="analyst@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ANALYST)
    main.app.dependency_overrides[get_current_user] = lambda: analyst
    yield analyst


@pytest.fixture(autouse=True)
def _no_real_shared_redis(monkeypatch):
    import src.market_data.sahmk.rate_limiter as rate_limiter_module
    import src.market_intelligence.scheduler_leader_lock as leader_lock_module

    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)
    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)


class _AlwaysLeaderLock:
    def try_acquire_or_renew(self, lease_seconds: float) -> bool:
        return True

    def release(self) -> None:
        pass


def _fake_live_sahmk_health():
    return {
        "configured_provider": "sahmk",
        "strict_real_data": False,
        "synthetic_allowed": True,
        "sahmk_key_present": True,
        "current_provider_kind": "sahmk",
        "last_connectivity_status": "SUCCESS",
        "last_connectivity_at": datetime.now(timezone.utc).isoformat(),
    }


def _seed_volume_spike_candidate(session_factory, symbol="2222"):
    """A symbol with a real, local abnormal-volume signal -- becomes a
    genuine Stage 1 candidate without any live SAHMK call."""
    session = session_factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    # Anchored near "now" (real wall-clock time) so Stage 1's OHLCV
    # staleness Data Quality Gate never rejects this fixture.
    base = datetime.now(timezone.utc) - timedelta(days=40)
    for i in range(40):
        close = Decimal("20.0") + (Decimal("0.1") if i % 2 == 0 else Decimal("-0.1"))
        volume = 60_000 if i == 39 else 10_000
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=close, high=close + Decimal("0.2"), low=close - Decimal("0.2"),
                close=close, volume=volume,
            )
        )
    session.commit()
    session.close()
    return stock


def test_radar_v2_scan_requires_staff_role(client, session_factory):
    non_staff = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff
    response = client.post("/api/v1/admin/market-intelligence/radar-v2/scan")
    assert response.status_code == 403


def test_radar_v2_opportunities_requires_staff_role(client, session_factory):
    non_staff = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/opportunities")
    assert response.status_code == 403


def test_radar_v2_opportunities_is_accessible_to_an_analyst(client, session_factory, as_analyst):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/opportunities")
    assert response.status_code == 200
    assert response.json() == []


def test_radar_v2_opportunity_detail_404s_for_a_missing_id(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/opportunities/999999")
    assert response.status_code == 404


def test_radar_v2_summary_on_an_empty_database(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["live_opportunity_count"] == 0
    assert body["live_by_classification"] == {}
    assert body["average_confidence"] is None
    assert body["most_recent_scan_run_id"] is None


def test_radar_v2_performance_on_an_empty_database_reports_null_rates(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/performance")
    assert response.status_code == 200
    body = response.json()
    assert body["total_opportunities_emitted"] == 0
    assert body["target_hit_rate"] is None
    assert body["stop_loss_hit_rate"] is None
    # Post-VAL-8 accumulation phase: the explicit minimum-sample gate
    # must reach the real HTTP response too.
    assert body["minimum_sample_size_required"] == 30
    assert body["sample_size_adequate"] is False
    assert body["accumulation_status"] == "INSUFFICIENT_DATA"


def test_radar_v2_extended_performance_on_an_empty_database_reports_empty_groups(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/performance/extended")
    assert response.status_code == 200
    body = response.json()
    assert body["win_rate_by_classification"] == []
    assert body["average_return_pct"] is None
    assert body["expected_calibration_error"] is None


def test_radar_v2_extended_performance_requires_staff_role(client, session_factory):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/performance/extended")
    assert response.status_code in (401, 403)


def test_radar_v2_extended_performance_exposes_the_new_cohort_fields(client, session_factory, as_staff):
    """RADAR-C Phase D extension: total_signals_by_classification and
    performance_by_market, plus the extended per-group fields
    (resolved_count/unresolved_count/target_hit_rate/stop_loss_hit_rate/
    average_risk_reward_realized/expectancy_pct/max_adverse_outcome_pct),
    must reach the real HTTP response, not just the dataclass."""
    from src.domain.models import DecisionV2Outcome, DecisionV2Snapshot, RadarOpportunity

    session = session_factory()
    stock = Stock(symbol="1111", name_en="Stock 1111", is_active=True, instrument_bucket="MAIN_MARKET_EQUITY")
    session.add(stock)
    session.commit()

    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision="BUY_CANDIDATE",
        decision_label_ar="شراء",
        confidence_score=75.0,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=100.0,
        market_status="OPEN",
        decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
        scan_run_id=1,
        downside_to_stop=2.0,
    )
    session.add(snapshot)
    session.commit()

    opportunity = RadarOpportunity(
        decision_v2_snapshot_id=snapshot.id,
        stock_id=stock.id,
        symbol=stock.symbol,
        classification="BUY_CANDIDATE",
        classification_label_ar="شراء",
        confidence_score=75.0,
        stage1_ranking_score=80.0,
        stage1_rank=1,
        stage1_signals=[],
        scan_run_id=1,
        emitted_at=datetime.now(timezone.utc),
    )
    session.add(opportunity)

    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        symbol=stock.symbol,
        status="TARGET_1_HIT",
        return_pct=6.0,
        entry_price=100.0,
        due_at=snapshot.decision_timestamp + timedelta(days=30),
    )
    session.add(outcome)
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/radar-v2/performance/extended")
    assert response.status_code == 200
    body = response.json()

    assert body["total_signals_by_classification"] == {"BUY_CANDIDATE": 1}

    group = next(g for g in body["win_rate_by_classification"] if g["label"] == "BUY_CANDIDATE")
    assert group["signal_count"] == 1
    assert group["resolved_count"] == 1
    assert group["unresolved_count"] == 0
    assert group["target_hit_rate"] == 1.0
    assert group["stop_loss_hit_rate"] == 0.0
    assert group["win_rate"] == 1.0
    assert group["average_risk_reward_realized"] == pytest.approx(3.0)
    assert group["expectancy_pct"] == pytest.approx(6.0)
    assert group["max_adverse_outcome_pct"] == pytest.approx(6.0)
    # 1 resolved outcome is real, but far below the 30-sample gate.
    assert group["sample_size_adequate"] is False

    market_group = next(g for g in body["performance_by_market"] if g["label"] == "Main Market")
    assert market_group["signal_count"] == 1
    assert market_group["win_rate"] == 1.0


def test_radar_v2_sahmk_consumption_never_leaks_the_api_key(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")
    assert response.status_code == 200
    body_text = response.text
    assert "sahmk_api_key" not in body_text.lower()
    assert "api_key" not in body_text.lower()


def test_radar_v2_sahmk_consumption_extracts_the_compound_operation_keys(
    client, session_factory, as_staff, monkeypatch
):
    """Regression test for a real production bug (2026-08-18 real-market
    validation audit): the underlying rate-limiter/cache telemetry keys
    its `by_operation` dict with compound "<operation>:<endpoint>"
    strings (e.g. "radar_v2:quote"), never a bare "radar_v2" key. The
    route must extract every radar_v2-prefixed entry -- and only those,
    excluding other operations' entries -- rather than doing an exact-
    match lookup that can never hit anything."""
    from src.api.routes.admin import market_intelligence as admin_mi_module
    from src.market_data.caching import redis_shared_cache as cache_module

    class _FakeRateLimiter:
        def get_status(self):
            return {
                "by_operation": {
                    "radar_v2:quote": 32,
                    "radar_v2:market_summary": 4,
                    "market_scan:quote": 500,
                }
            }

    monkeypatch.setattr(admin_mi_module, "get_default_rate_limiter", lambda: _FakeRateLimiter())
    monkeypatch.setattr(
        cache_module,
        "get_observability_snapshot",
        lambda caches: {
            "by_operation": {
                "radar_v2:quote": 10,
                "ingestion:ohlcv": 999,
            }
        },
    )

    response = client.get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")

    assert response.status_code == 200
    body = response.json()
    assert body["rate_limiter_by_operation"] == {"radar_v2:quote": 32, "radar_v2:market_summary": 4}
    assert body["cache_by_operation"] == {"radar_v2:quote": 10}


def test_radar_v2_sahmk_consumption_reports_none_when_nothing_attributable(
    client, session_factory, as_staff, monkeypatch
):
    """When the telemetry has real data but none of it is radar_v2-
    tagged, the route must honestly report None rather than an empty
    dict or a fabricated zero."""
    from src.api.routes.admin import market_intelligence as admin_mi_module
    from src.market_data.caching import redis_shared_cache as cache_module

    class _FakeRateLimiter:
        def get_status(self):
            return {"by_operation": {"market_scan:quote": 500}}

    monkeypatch.setattr(admin_mi_module, "get_default_rate_limiter", lambda: _FakeRateLimiter())
    monkeypatch.setattr(
        cache_module,
        "get_observability_snapshot",
        lambda caches: {"by_operation": {"ingestion:ohlcv": 999}},
    )

    response = client.get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")

    assert response.status_code == 200
    body = response.json()
    assert body["rate_limiter_by_operation"] is None
    assert body["cache_by_operation"] is None


def test_radar_v2_scan_with_no_stage1_candidates_spends_zero_sahmk_and_writes_nothing(
    client, session_factory, as_staff, monkeypatch
):
    """An empty/quiet universe (no PriceBar rows at all) yields zero
    Stage 1 candidates -- the route must never even attempt Stage 2."""
    from src.api.routes.admin import market_intelligence as admin_mi_module
    from src.market_data import provider_factory

    monkeypatch.setattr(admin_mi_module, "SchedulerLeaderLock", _AlwaysLeaderLock)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_live_sahmk_health)

    response = client.post("/api/v1/admin/market-intelligence/radar-v2/scan")

    assert response.status_code == 200
    body = response.json()
    assert body["stage2_executed"] is False
    assert body["stage2_stop_reason"] == "no_stage1_candidates"
    assert body["opportunities_emitted"] == []
    assert body["scan_run_id"] is None


def test_radar_v2_scan_happy_path_emits_a_real_opportunity(client, session_factory, as_staff, monkeypatch):
    """The full pass: a real Stage 1 candidate goes through the exact
    same bounded Stage 2 cycle continue-scan-cycle uses, and a
    RadarOpportunity row is written for the resulting DecisionV2Snapshot."""
    from src.api.routes.admin import market_intelligence as admin_mi_module
    from src.market_data import provider_factory

    _seed_volume_spike_candidate(session_factory, "2222")

    monkeypatch.setattr(admin_mi_module, "SchedulerLeaderLock", _AlwaysLeaderLock)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_live_sahmk_health)

    fake_provider = DevMarketDataProvider()

    async def _fake_get_provider(force_refresh=False):
        return fake_provider

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)

    response = client.post("/api/v1/admin/market-intelligence/radar-v2/scan")

    assert response.status_code == 200
    body = response.json()
    assert body["stage1_candidate_count"] >= 1
    assert body["stage2_symbols_selected"] == ["2222"]
    assert body["stage2_executed"] is True
    assert body["stage2_stop_reason"] is None
    assert body["scan_run_id"] is not None
    assert len(body["opportunities_emitted"]) == 1
    emitted = body["opportunities_emitted"][0]
    assert emitted["symbol"] == "2222"
    assert emitted["stage1_rank"] == 1

    # The opportunity must now be visible through the list/detail/summary
    # routes too -- not just in the scan response.
    list_response = client.get("/api/v1/admin/market-intelligence/radar-v2/opportunities")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    detail_response = client.get(
        f"/api/v1/admin/market-intelligence/radar-v2/opportunities/{emitted['id']}"
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["symbol"] == "2222"
    assert "stage1_component_scores" in detail

    # Phase 4 (Advanced Technical Engine exposure): the already-computed
    # DecisionV2Snapshot technical fields must reach the consumer detail
    # response -- these are keys that must exist regardless of value,
    # since some (e.g. support/resistance) are legitimately None when
    # the real engine can't derive them from the seeded bar history.
    for field in (
        "trend_direction_ar",
        "trend_strength_label_ar",
        "nearest_support",
        "major_support",
        "nearest_resistance",
        "major_resistance",
        "breakout_level",
        "breakdown_level",
        "support_resistance_evidence_ar",
        "current_volume",
        "average_volume",
        "accumulation_score",
        "entry_quality_label_ar",
        "entry_status_label_ar",
        "why_now_ar",
        "why_not_stronger_ar",
        "why_not_buy_reasons",
    ):
        assert field in detail

    summary_response = client.get("/api/v1/admin/market-intelligence/radar-v2/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["live_opportunity_count"] == 1


def test_radar_v2_scan_never_touches_the_critical_reserve(client, session_factory, as_staff, monkeypatch):
    """Phase E's explicit requirement: protected/critical SAHMK quota
    must never be spent by background radar work. Radar V2's Stage 2
    call always runs under priority_scope(BACKGROUND) (inherited,
    unmodified, from _run_one_bounded_background_cycle) -- proven here
    directly by reading the real rate limiter's critical counter before
    and after a real scan that DID execute and DID spend background
    quota."""
    from src.api.routes.admin import market_intelligence as admin_mi_module
    from src.market_data import provider_factory
    from src.market_data.sahmk.rate_limiter import get_default_rate_limiter

    _seed_volume_spike_candidate(session_factory, "2222")

    monkeypatch.setattr(admin_mi_module, "SchedulerLeaderLock", _AlwaysLeaderLock)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_live_sahmk_health)

    fake_provider = DevMarketDataProvider()

    async def _fake_get_provider(force_refresh=False):
        return fake_provider

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)

    # Delta, not an absolute value: the shared, process-wide rate
    # limiter singleton may already carry state from unrelated tests
    # earlier in the same pytest session (unrelated to Radar V2) --
    # the real invariant under test is that THIS call adds nothing to
    # the critical counter, whatever it started at.
    critical_before = get_default_rate_limiter().get_status()["critical_requests_used_today"]

    response = client.post("/api/v1/admin/market-intelligence/radar-v2/scan")

    assert response.status_code == 200
    assert response.json()["stage2_executed"] is True

    critical_after = get_default_rate_limiter().get_status()["critical_requests_used_today"]
    assert critical_after == critical_before


def test_radar_v2_scan_never_exceeds_the_configured_candidate_cap(
    client, session_factory, as_staff, monkeypatch
):
    """A hard structural guarantee: even with many real Stage 1
    candidates, Stage 2 is only ever asked to validate the configured
    cap's worth of symbols."""
    from src.api.routes.admin import market_intelligence as admin_mi_module
    from src.market_data import provider_factory

    for i in range(5):
        _seed_volume_spike_candidate(session_factory, symbol=str(1000 + i))

    monkeypatch.setenv("RADAR_STAGE2_CANDIDATE_CAP", "2")
    monkeypatch.setattr(admin_mi_module, "SchedulerLeaderLock", _AlwaysLeaderLock)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_live_sahmk_health)

    fake_provider = DevMarketDataProvider()

    async def _fake_get_provider(force_refresh=False):
        return fake_provider

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)

    response = client.post("/api/v1/admin/market-intelligence/radar-v2/scan")

    assert response.status_code == 200
    body = response.json()
    assert body["stage1_candidate_count"] == 5
    assert body["stage2_candidate_cap"] == 2
    assert len(body["stage2_symbols_selected"]) == 2
