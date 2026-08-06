"""Integration tests for POST /api/v1/admin/market-intelligence/diagnostic-scan.

Covers: staff-only gating, the "no publish without a real SAHMK
connectivity result" safety rule, secret redaction, and the happy path
actually running run_market_scan_job and persisting real
SymbolIntelligenceRecord rows.

Same double-monkeypatch as test_market_routes.py/test_backtests_routes.py:
the route handler uses Depends(get_db) (overridable normally), but
run_market_scan_job gets its session factory via a *local* `from
src.core.db.database import get_session_factory` call inside the route
-- so database.get_session_factory itself must be monkeypatched too.
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
from src.domain.models import (
    DecisionV2Snapshot,
    MarketScanRun,
    MarketScanStatus,
    PriceBar,
    RecommendationLabel,
    StaffRole,
    Stock,
    SymbolIntelligenceRecord,
    Timeframe,
    User,
)
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


def _seed_stock_with_bars(session_factory, symbol, sector="Energy", count=80, price_step=0.08):
    session = session_factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    for i in range(count):
        price += price_step
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(price)), high=Decimal(str(price + 0.5)), low=Decimal(str(price - 0.5)),
                close=Decimal(str(price)), volume=1000 + i,
            )
        )
    session.commit()
    session.close()


def test_non_staff_user_gets_403(client, session_factory):
    non_staff = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff

    response = client.post("/api/v1/admin/market-intelligence/diagnostic-scan", json={})

    assert response.status_code == 403


def test_no_scan_runs_when_sahmk_is_not_the_selected_provider(client, session_factory, as_staff, monkeypatch):
    """The core safety rule: if the real connectivity probe did not
    select SAHMK (e.g. unreachable, or STRICT_REAL_DATA blocked it),
    the route must never run a scan or write a recommendation row."""
    from src.market_data import provider_factory

    async def _fake_get_provider(force_refresh=False):
        return object()

    def _fake_health():
        return {
            "configured_provider": "sahmk",
            "strict_real_data": True,
            "synthetic_allowed": False,
            "sahmk_key_present": False,
            "current_provider_kind": None,
            "last_connectivity_status": "FAILED",
            "last_connectivity_at": None,
            "last_real_data_at": None,
        }

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_health)

    response = client.post("/api/v1/admin/market-intelligence/diagnostic-scan", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["current_provider_kind"] is None
    assert body["run_id"] is None
    assert body["rows_written"] == 0
    assert body["can_publish_recommendations"] is False
    assert body["sahmk_key_present"] is False


def test_happy_path_runs_the_real_scan_path_and_persists_rows(client, session_factory, as_staff, monkeypatch):
    """When the real provider selection resolves to "sahmk", the route
    must run the exact same run_market_scan_job/execute_scan path the
    scheduler uses and report real, persisted evidence back."""
    from src.market_data import provider_factory

    _seed_stock_with_bars(session_factory, "2222")

    fake_provider = DevMarketDataProvider()

    async def _fake_get_provider(force_refresh=False):
        return fake_provider

    def _fake_health():
        return {
            "configured_provider": "sahmk",
            "strict_real_data": False,
            "synthetic_allowed": True,
            "sahmk_key_present": True,
            "current_provider_kind": "sahmk",
            "last_connectivity_status": "SUCCESS",
            "last_connectivity_at": datetime.now(timezone.utc).isoformat(),
            "last_real_data_at": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_health)

    response = client.post(
        "/api/v1/admin/market-intelligence/diagnostic-scan", json={"symbols": ["2222"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] is not None
    assert body["run_status"] == "SUCCESS"
    assert body["symbols_requested"] == 1
    assert body["symbols_succeeded"] == 1
    assert body["rows_written"] == 1
    assert body["sample_symbols"][0]["symbol"] == "2222"
    assert body["last_scan_source"] == "SAHMK_REAL"
    assert body["can_publish_recommendations"] is True
    assert body["data_is_fresh"] is True
    # Phase 3A: the same scan run also computed and persisted a
    # DecisionV2Snapshot for this symbol, with scan_run_id set to this
    # diagnostic run -- proves the scheduled-scan pipeline (not just
    # the on-demand /decision-v2 route) now produces V2 evidence.
    assert body["decision_v2_rows_written"] == 1
    assert body["decision_v2_sample"][0]["symbol"] == "2222"
    assert body["decision_v2_sample"][0]["scan_run_id"] == body["run_id"]
    assert body["decision_v2_sample"][0]["decision"]
    # This run is itself now the "latest completed run" -- the two
    # independent lookups must agree.
    assert body["latest_completed_run_id"] == body["run_id"]
    assert body["latest_completed_run_v1_rows_written"] == 1
    assert body["latest_completed_run_decision_v2_rows_written"] == 1
    assert body["latest_completed_run_decision_v2_sample"][0]["symbol"] == "2222"


def test_secret_never_appears_in_the_response(client, session_factory, as_staff, monkeypatch):
    """Even when a real SAHMK error message could plausibly contain
    request context, the response body must never contain the raw
    SAHMK_API_KEY value."""
    from src.market_data import provider_factory

    secret_value = "sk_live_super_secret_sahmk_key_00000000000000000000000000"
    monkeypatch.setenv("SAHMK_API_KEY", secret_value)

    async def _raise(force_refresh=False):
        # Deliberately embeds the *full* secret value, as if some deep
        # exception message leaked it -- proves the route's own scrub
        # step catches it, not just that this particular test's fake
        # message happened to omit it.
        raise RuntimeError(f"connection failed, Authorization: Bearer {secret_value}")

    def _fake_health():
        return {
            "configured_provider": "sahmk",
            "strict_real_data": False,
            "synthetic_allowed": True,
            "sahmk_key_present": True,
            "current_provider_kind": None,
            "last_connectivity_status": "FAILED",
            "last_connectivity_at": None,
            "last_real_data_at": None,
        }

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _raise)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_health)

    response = client.post("/api/v1/admin/market-intelligence/diagnostic-scan", json={})

    assert response.status_code == 200
    assert secret_value not in response.text
    assert "***" in response.json()["sahmk_error"]


def test_overlap_skip_still_reports_evidence_from_the_latest_completed_run(
    client, session_factory, as_staff, monkeypatch
):
    """Real production behavior observed live: when the Live Market
    Mode scheduler already has a scan RUNNING, this route's own overlap
    guard correctly skips starting a second one (run_id/run_status come
    back None) -- but that must never mean the response reports zero
    evidence. The latest_completed_run_* fields must still surface real
    V1 + Decision V2 output from the most recent *finished* run, which
    is the only reliable way to observe the scheduler's own real
    output when a fresh diagnostic dispatch collides with it."""
    from src.market_data import provider_factory

    session = session_factory()
    stock = Stock(symbol="2222", name_en="Stock 2222", name_ar="سهم", sector="Energy")
    session.add(stock)
    session.commit()

    completed_run = MarketScanRun(status=MarketScanStatus.SUCCESS, symbols_requested=1, symbols_succeeded=1)
    session.add(completed_run)
    session.commit()
    completed_run_id = completed_run.id
    session.add(
        SymbolIntelligenceRecord(
            scan_run_id=completed_run.id, stock_id=stock.id, symbol="2222",
            recommendation=RecommendationLabel.BUY, confidence=70.0, final_score=65.0,
            risk_level="MEDIUM", time_horizon="SHORT_TERM", position_size="STANDARD",
            evaluated_at=datetime.now(timezone.utc), engine_version="1.0.0",
        )
    )
    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id, symbol="2222", company_name_en="Stock 2222",
            decision="BUY_CANDIDATE", decision_label_ar="مرشح شراء",
            confidence_score=70.0, opportunity_quality_score=60.0, risk_score=40.0,
            data_quality_score=80.0, data_freshness_status="LIVE",
            market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
            recommendation_basis="test", analysis_version="2.0.0", data_source="SAHMK_REAL",
            scan_run_id=completed_run_id,
        )
    )
    # A second run currently RUNNING -- the condition this route's
    # overlap guard exists to detect.
    session.add(MarketScanRun(status=MarketScanStatus.RUNNING, symbols_requested=3))
    session.commit()
    session.close()

    def _fake_health():
        return {
            "configured_provider": "sahmk",
            "strict_real_data": True,
            "synthetic_allowed": False,
            "sahmk_key_present": True,
            "current_provider_kind": "sahmk",
            "last_connectivity_status": "SUCCESS",
            "last_connectivity_at": datetime.now(timezone.utc).isoformat(),
            "last_real_data_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _fake_get_provider(force_refresh=False):
        return DevMarketDataProvider()

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)
    monkeypatch.setattr(provider_factory, "get_market_data_health", _fake_health)

    response = client.post("/api/v1/admin/market-intelligence/diagnostic-scan", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] is None
    assert "already in progress" in body["sahmk_error"]
    assert body["latest_completed_run_id"] == completed_run_id
    assert body["latest_completed_run_v1_rows_written"] == 1
    assert body["latest_completed_run_v1_sample_symbols"][0]["symbol"] == "2222"
    assert body["latest_completed_run_decision_v2_rows_written"] == 1
    assert body["latest_completed_run_decision_v2_sample"][0]["symbol"] == "2222"
    assert body["latest_completed_run_decision_v2_sample"][0]["decision"] == "BUY_CANDIDATE"


# --- GET /coverage -------------------------------------------------------


def test_coverage_requires_staff_role(client, session_factory):
    non_staff = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 403


def test_coverage_reports_real_stock_and_price_history_counts(client, session_factory, as_staff):
    """The direct evidence this endpoint exists for: exact active/
    inactive Stock counts and how many of the active ones actually have
    price history (the real SymbolSelector eligibility condition) --
    not an estimate, a real query result."""
    _seed_stock_with_bars(session_factory, "2222", count=5)  # active, has bars

    session = session_factory()
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank", is_active=True))  # active, no bars yet
    session.add(
        Stock(
            symbol="4342", name_en="Some REIT Fund", is_active=False,
            instrument_bucket="REIT", exclusion_reason="security_type='REIT'",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["total_stocks"] == 3
    assert body["active_stocks"] == 2
    assert body["inactive_stocks"] == 1
    assert body["stocks_with_price_history"] == 1
    assert body["stocks_without_price_history"] == 1
    assert body["coverage_pct"] == pytest.approx(50.0)

    buckets = {row["bucket"]: row["count"] for row in body["instrument_bucket_counts"]}
    assert buckets["REIT"] == 1
    assert buckets[None] == 2  # 2222/1120 predate universe classification


def test_coverage_reports_ingestion_scheduler_configuration(client, session_factory, as_staff, monkeypatch):
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_ingestion_symbol_universe",
        lambda: ["2222", "1120", "2010"],
    )
    monkeypatch.setattr(
        "src.market_data.ingestion.config.is_symbol_auto_discovery_enabled", lambda: True
    )

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["ingestion_auto_discover_enabled"] is True
    assert body["ingestion_configured_seed_symbols"] == 3


def test_coverage_reports_the_latest_run_of_every_ingestion_job(client, session_factory, as_staff):
    from src.domain.models import IngestionJobStatus, IngestionRunLog

    session = session_factory()
    now = datetime.now(timezone.utc)
    session.add(
        IngestionRunLog(
            job_name="symbols", started_at=now - timedelta(hours=2), finished_at=now - timedelta(hours=1, minutes=58),
            duration_seconds=Decimal("120.5"), symbols_requested=250, symbols_succeeded=248, symbols_failed=2,
            rows_upserted=250, status=IngestionJobStatus.PARTIAL, error_summary="2 symbols failed",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    by_job = {row["job_name"]: row for row in body["latest_ingestion_runs"]}
    assert set(by_job.keys()) == {"symbols", "historical_ohlcv", "fundamentals", "dividends"}
    assert by_job["symbols"]["status"] == "partial"
    assert by_job["symbols"]["symbols_requested"] == 250
    assert by_job["symbols"]["symbols_succeeded"] == 248
    assert by_job["historical_ohlcv"]["status"] is None  # never run yet


def test_coverage_reports_the_latest_scan_run(client, session_factory, as_staff):
    session = session_factory()
    session.add(
        MarketScanRun(
            status=MarketScanStatus.SUCCESS, symbols_requested=250, symbols_succeeded=245,
            symbols_skipped=0, symbols_failed=5, duration_seconds=Decimal("310.2"),
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_scan_run"]["status"] == "SUCCESS"
    assert body["latest_scan_run"]["symbols_requested"] == 250
    assert body["latest_scan_run"]["symbols_succeeded"] == 245


def test_coverage_handles_an_entirely_empty_database(client, session_factory, as_staff):
    """No stocks, no ingestion runs, no scan runs yet -- must report
    real zeros/nulls, never crash or fabricate a number."""
    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["total_stocks"] == 0
    assert body["active_stocks"] == 0
    assert body["coverage_pct"] is None
    assert body["latest_scan_run"] is None
