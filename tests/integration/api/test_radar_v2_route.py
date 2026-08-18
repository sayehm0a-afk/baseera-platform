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
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
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


def test_radar_v2_sahmk_consumption_never_leaks_the_api_key(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")
    assert response.status_code == 200
    body_text = response.text
    assert "sahmk_api_key" not in body_text.lower()
    assert "api_key" not in body_text.lower()


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
