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
    Dividend,
    FundamentalSnapshot,
    MarketScanRun,
    MarketScanStatus,
    PeriodType,
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


def test_coverage_is_accessible_to_an_analyst_account(client, session_factory):
    analyst = User(email="analyst@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ANALYST)
    main.app.dependency_overrides[get_current_user] = lambda: analyst

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200


def test_full_discovery_rejects_an_analyst_account(client, session_factory):
    # Mutating/triggering routes stay ADMIN-only -- an analyst gaining
    # read access to /coverage must not also gain the power to kick off
    # a real ingestion pass.
    analyst = User(email="analyst@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ANALYST)
    main.app.dependency_overrides[get_current_user] = lambda: analyst

    response = client.post("/api/v1/admin/market-intelligence/full-discovery")

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


def test_coverage_reports_main_nomu_split_and_excluded_instrument_counts(client, session_factory, as_staff):
    session = session_factory()
    session.add(Stock(symbol="2222", name_en="Saudi Aramco", is_active=True, instrument_bucket="MAIN_MARKET_EQUITY"))
    session.add(Stock(symbol="9999", name_en="Nomu Co", is_active=True, instrument_bucket="NOMU_EQUITY"))
    session.add(
        Stock(
            symbol="4342", name_en="Some REIT Fund", is_active=False,
            instrument_bucket="REIT", exclusion_reason="security_type='REIT'",
        )
    )
    session.add(
        Stock(
            symbol="8010", name_en="Some ETF", is_active=False,
            instrument_bucket="ETF_FUND", exclusion_reason="is_etf=True",
        )
    )
    session.add(Stock(symbol="1010", name_en="Never classified", is_active=True))
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["main_market_stocks"] == 1
    assert body["nomu_market_stocks"] == 1
    assert body["total_excluded_non_equity"] == 2
    excluded = {row["bucket"]: row["count"] for row in body["excluded_instrument_counts"]}
    assert excluded == {"REIT": 1, "ETF_FUND": 1}
    # total(5) - main(1) - nomu(1) - excluded(2) = 1 (the never-classified row)
    assert body["unclassified_market_segment_stocks"] == 1


def test_coverage_reports_fundamentals_and_dividend_counts(client, session_factory, as_staff):
    session = session_factory()
    with_fundamentals = Stock(symbol="2222", name_en="Saudi Aramco", is_active=True)
    with_dividend = Stock(symbol="1120", name_en="Al Rajhi Bank", is_active=True)
    bare = Stock(symbol="1180", name_en="No fundamentals or dividends", is_active=True)
    session.add_all([with_fundamentals, with_dividend, bare])
    session.commit()
    session.add(
        FundamentalSnapshot(
            stock_id=with_fundamentals.id, period_type=PeriodType.ANNUAL,
            fiscal_period_end=datetime(2025, 12, 31).date(), revenue=Decimal("1000"),
            net_income=Decimal("100"), total_assets=Decimal("5000"), total_liabilities=Decimal("2000"),
            total_equity=Decimal("3000"), source="sahmk",
        )
    )
    session.add(
        Dividend(
            stock_id=with_dividend.id, ex_date=datetime(2026, 1, 1).date(),
            amount_per_share=Decimal("1.5"), source="sahmk",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["stocks_with_fundamentals"] == 1
    assert body["stocks_without_fundamentals"] == 2
    assert body["stocks_with_dividends"] == 1
    assert body["stocks_without_dividends"] == 2


def test_coverage_reports_per_sector_breakdown(client, session_factory, as_staff):
    _seed_stock_with_bars(session_factory, "2222", sector="Energy", count=5)
    session = session_factory()
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank", sector="Banks", is_active=True))
    session.add(Stock(symbol="4030", name_en="No sector yet", sector=None, is_active=True))
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    by_sector = {row["sector"]: row for row in body["sector_coverage"]}
    assert by_sector["Energy"]["total_stocks"] == 1
    assert by_sector["Energy"]["stocks_with_price_history"] == 1
    assert by_sector["Energy"]["coverage_pct"] == pytest.approx(100.0)
    assert by_sector["Banks"]["total_stocks"] == 1
    assert by_sector["Banks"]["stocks_with_price_history"] == 0
    assert by_sector["Banks"]["coverage_pct"] == pytest.approx(0.0)
    assert by_sector[None]["total_stocks"] == 1


def test_coverage_reports_decision_engine_entry_and_recommendation_counts_for_latest_scan(
    client, session_factory, as_staff
):
    session = session_factory()
    scan = MarketScanRun(status=MarketScanStatus.SUCCESS, symbols_requested=2, symbols_succeeded=2)
    session.add(scan)
    session.commit()
    stock = Stock(symbol="2222", name_en="Saudi Aramco", sector="Energy", is_active=True)
    session.add(stock)
    session.commit()
    session.add(
        SymbolIntelligenceRecord(
            scan_run_id=scan.id, stock_id=stock.id, symbol="2222", recommendation=RecommendationLabel.BUY,
            confidence=Decimal("70"), final_score=Decimal("65"), evaluated_at=datetime.now(timezone.utc),
            engine_version="v1",
        )
    )
    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id, symbol="2222", company_name_en="Saudi Aramco", decision="BUY_CANDIDATE",
            decision_label_ar="شراء", confidence_score=Decimal("70"),
            opportunity_quality_score=Decimal("60"), risk_score=Decimal("30"), data_quality_score=Decimal("90"),
            data_freshness_status="FRESH", market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
            analysis_version="v2", data_source="SAHMK_REAL", scan_run_id=scan.id,
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_scan_symbols_entering_decision_engine"] == 1
    assert body["latest_scan_recommendations_generated"] == 1


def test_coverage_reports_exact_symbols_missing_price_history(client, session_factory, as_staff):
    """Root-caused in production: 408/408 OHLCV syncs reported success
    but only 393 stocks had real PriceBar rows -- the aggregate count
    gave no way to find which 15. This is the exact-symbol fix."""
    _seed_stock_with_bars(session_factory, "2222", count=5)  # has bars
    session = session_factory()
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank", is_active=True))  # active, no bars
    session.add(Stock(symbol="4342", name_en="Some REIT", is_active=False))  # inactive, excluded regardless
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    assert response.json()["symbols_missing_price_history"] == ["1120"]


def test_coverage_reports_latest_scan_skipped_symbols_from_the_authoritative_summary_column(
    client, session_factory, as_staff
):
    """When skipped_symbols_summary was written by the scan itself
    (MarketIntelligenceEngine._build_skipped_symbols_summary), that's
    the real per-symbol reason -- use it directly, not a diff guess."""
    session = session_factory()
    session.add(
        MarketScanRun(
            status=MarketScanStatus.SUCCESS, symbols_requested=3, symbols_succeeded=1, symbols_skipped=2,
            skipped_symbols_summary="9999: insufficient_data; 8888: stock_not_registered",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    assert response.json()["latest_scan_skipped_symbols"] == ["9999", "8888"]


def test_coverage_reconstructs_latest_scan_skipped_symbols_when_the_summary_predates_the_fix(
    client, session_factory, as_staff
):
    """A scan run from before skipped_symbols_summary existed (e.g. the
    real production run 98) has that column null -- falls back to a
    real diff: active/price-history-eligible symbols minus symbols that
    actually got a SymbolIntelligenceRecord for that run."""
    _seed_stock_with_bars(session_factory, "2222", count=5)
    _seed_stock_with_bars(session_factory, "1120", count=5)

    session = session_factory()
    scan = MarketScanRun(
        status=MarketScanStatus.SUCCESS, symbols_requested=2, symbols_succeeded=1, symbols_skipped=1,
    )
    session.add(scan)
    session.commit()
    stock = session.query(Stock).filter_by(symbol="2222").one()
    session.add(
        SymbolIntelligenceRecord(
            scan_run_id=scan.id, stock_id=stock.id, symbol="2222", recommendation=RecommendationLabel.BUY,
            confidence=Decimal("70"), final_score=Decimal("65"), evaluated_at=datetime.now(timezone.utc),
            engine_version="v1",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    assert response.json()["latest_scan_skipped_symbols"] == ["1120"]


def test_coverage_reports_db_consistency_gaps(client, session_factory, as_staff):
    session = session_factory()
    # Active but missing instrument_bucket/sector/exchange.
    session.add(Stock(symbol="2222", name_en="Missing classification", is_active=True))
    # Inactive but missing exclusion_reason (a real inconsistency to surface).
    session.add(Stock(symbol="4342", name_en="Excluded, no reason recorded", is_active=False))
    # Active but has an exclusion_reason set (also a real inconsistency).
    session.add(
        Stock(
            symbol="1010", name_en="Active with stale exclusion_reason", is_active=True,
            exclusion_reason="security_type='REIT'",
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    consistency = response.json()["db_consistency"]
    assert consistency["active_stocks_missing_instrument_bucket"] == 2
    assert consistency["active_stocks_missing_sector"] == 2
    assert consistency["active_stocks_missing_exchange"] == 2
    assert consistency["inactive_stocks_missing_exclusion_reason"] == 1
    assert consistency["active_stocks_with_exclusion_reason_set"] == 1


def test_coverage_pipeline_funnel_stages_are_all_present_with_reasons(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/coverage")

    assert response.status_code == 200
    stages = response.json()["pipeline_funnel"]
    stage_names = [s["stage"] for s in stages]
    assert stage_names == [
        "Discovery (total Stock rows)",
        "Eligibility (active, non-excluded)",
        "OHLCV ingested",
        "Fundamentals ingested",
        "Dividends ingested",
        "Entered Decision Engine (latest scan)",
        "Recommendations generated (latest scan)",
    ]
    for stage in stages:
        assert stage["reason"]
        assert stage["dropped"] >= 0


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
    assert body["main_market_stocks"] == 0
    assert body["nomu_market_stocks"] == 0
    assert body["unclassified_market_segment_stocks"] == 0
    assert body["excluded_instrument_counts"] == []
    assert body["total_excluded_non_equity"] == 0
    assert body["stocks_with_fundamentals"] == 0
    assert body["stocks_without_fundamentals"] == 0
    assert body["stocks_with_dividends"] == 0
    assert body["stocks_without_dividends"] == 0
    assert body["sector_coverage"] == []
    assert body["latest_scan_symbols_entering_decision_engine"] == 0
    assert body["latest_scan_recommendations_generated"] == 0
    assert body["db_consistency"] == {
        "active_stocks_missing_instrument_bucket": 0,
        "active_stocks_missing_sector": 0,
        "active_stocks_missing_exchange": 0,
        "inactive_stocks_missing_exclusion_reason": 0,
        "active_stocks_with_exclusion_reason_set": 0,
    }
    assert len(body["pipeline_funnel"]) == 7


# --- POST /full-discovery ------------------------------------------------


def test_full_discovery_requires_staff_role(client, session_factory):
    non_staff = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff

    response = client.post("/api/v1/admin/market-intelligence/full-discovery")

    assert response.status_code == 403


def test_full_discovery_accepts_and_runs_the_real_ingestion_jobs(client, session_factory, as_staff, monkeypatch):
    """DevMarketDataProvider is used throughout this test module's
    fixtures -- has no get_symbol_directory support, so sync_symbols
    logs "skip discovery" and succeeds with zero symbols requested;
    the point of this test is that the route accepts the request, runs
    the real IngestionScheduler.run_all_jobs_once() job sequence (not a
    parallel implementation), and persists real IngestionRunLog rows
    for all four jobs -- proving the wiring, independent of how many
    real symbols a given provider happens to discover."""
    from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider

    async def _get_dev_market_provider():
        return DevMarketDataProvider()

    async def _get_dev_fundamental_provider():
        return DevFundamentalDataProvider()

    monkeypatch.setattr("src.market_data.ingestion.scheduler.get_market_data_provider", _get_dev_market_provider)
    monkeypatch.setattr(
        "src.market_data.ingestion.scheduler.get_fundamental_data_provider", _get_dev_fundamental_provider
    )

    response = client.post("/api/v1/admin/market-intelligence/full-discovery")

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["job_names"] == ["symbols", "historical_ohlcv", "fundamentals", "dividends"]

    session = session_factory()
    from src.domain.models import IngestionRunLog

    logged_jobs = {row.job_name for row in session.query(IngestionRunLog).all()}
    session.close()
    assert logged_jobs == {"symbols", "historical_ohlcv", "fundamentals", "dividends"}


def test_full_discovery_reports_overlap_when_a_job_is_already_running(client, session_factory, as_staff):
    from src.domain.models import IngestionJobStatus, IngestionRunLog

    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="symbols", started_at=datetime.now(timezone.utc), status=IngestionJobStatus.RUNNING
        )
    )
    session.commit()
    session.close()

    response = client.post("/api/v1/admin/market-intelligence/full-discovery")

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert body["job_names"] == []
    assert "already running" in body["message"]


def test_full_discovery_reaps_a_stale_running_row_instead_of_blocking_forever(
    client, session_factory, as_staff, monkeypatch
):
    """A process killed/restarted mid-run leaves an IngestionRunLog row
    RUNNING with no finished_at forever -- indistinguishable from a
    genuinely in-progress job to the naive in-flight check. Without the
    reap_stale_ingestion_runs call, one such row (as was found in
    production, stuck since a container restart days earlier) would
    permanently block every future full-discovery trigger. A row older
    than the configured max age must be reaped (marked FAILED) so a
    fresh trigger is accepted."""
    from src.domain.models import IngestionJobStatus, IngestionRunLog
    from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider

    monkeypatch.setenv("INGESTION_MAX_JOB_RUN_DURATION_HOURS", "6")

    session = session_factory()
    stale_started_at = datetime.now(timezone.utc) - timedelta(hours=100)
    session.add(
        IngestionRunLog(job_name="symbols", started_at=stale_started_at, status=IngestionJobStatus.RUNNING)
    )
    session.commit()
    stale_row_id = session.query(IngestionRunLog).filter_by(job_name="symbols").first().id
    session.close()

    async def _get_dev_market_provider():
        return DevMarketDataProvider()

    async def _get_dev_fundamental_provider():
        return DevFundamentalDataProvider()

    monkeypatch.setattr("src.market_data.ingestion.scheduler.get_market_data_provider", _get_dev_market_provider)
    monkeypatch.setattr(
        "src.market_data.ingestion.scheduler.get_fundamental_data_provider", _get_dev_fundamental_provider
    )

    response = client.post("/api/v1/admin/market-intelligence/full-discovery")

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["job_names"] == ["symbols", "historical_ohlcv", "fundamentals", "dividends"]

    session = session_factory()
    stale_row = session.query(IngestionRunLog).filter_by(id=stale_row_id).one()
    assert stale_row.status == IngestionJobStatus.FAILED
    assert stale_row.finished_at is not None
    assert "Reaped" in stale_row.error_summary
    session.close()


def test_full_discovery_still_blocks_on_a_genuinely_recent_running_row(client, session_factory, as_staff):
    """The reap only clears rows older than the configured max age --
    a job that started moments ago must still be treated as in-flight."""
    from src.domain.models import IngestionJobStatus, IngestionRunLog

    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="historical_ohlcv", started_at=datetime.now(timezone.utc), status=IngestionJobStatus.RUNNING
        )
    )
    session.commit()
    session.close()

    response = client.post("/api/v1/admin/market-intelligence/full-discovery")

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert "already running" in body["message"]


# --- GET /decision-intelligence -------------------------------------------


def _seed_decision_v2(
    session_factory,
    symbol,
    decision,
    confidence_score,
    risk_level=None,
    sector_ar=None,
    gates=None,
    decision_timestamp=None,
    company_name_ar=None,
):
    session = session_factory()
    stock = session.query(Stock).filter(Stock.symbol == symbol).first()
    if stock is None:
        stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector_ar)
        session.add(stock)
        session.commit()
    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id,
            symbol=symbol,
            company_name_ar=company_name_ar,
            company_name_en=f"Stock {symbol}",
            sector_ar=sector_ar,
            decision=decision,
            decision_label_ar="test",
            confidence_score=Decimal(str(confidence_score)),
            opportunity_quality_score=Decimal("50"),
            risk_score=Decimal("50"),
            data_quality_score=Decimal("100"),
            data_freshness_status="LIVE",
            market_status="OPEN",
            decision_timestamp=decision_timestamp or datetime.now(timezone.utc),
            analysis_version="2.0.0",
            data_source="SAHMK_REAL",
            risk_level=risk_level,
            gates=gates or [],
        )
    )
    session.commit()
    session.close()


def test_decision_intelligence_requires_staff_role(client, session_factory):
    non_staff = User(email="user@example.com", password_hash="hashed", is_staff=False)
    main.app.dependency_overrides[get_current_user] = lambda: non_staff

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 403


def test_decision_intelligence_reports_real_decision_and_confidence_distribution(client, session_factory, as_staff):
    _seed_decision_v2(session_factory, "2222", "STRONG_BUY_CANDIDATE", 92.0, risk_level="LOW", sector_ar="الطاقة")
    _seed_decision_v2(session_factory, "1120", "BUY_CANDIDATE", 78.0, risk_level="MEDIUM", sector_ar="البنوك")
    _seed_decision_v2(session_factory, "1180", "HOLD", 55.0, risk_level="MEDIUM", sector_ar="البنوك")

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 200
    body = response.json()
    assert body["total_symbols_evaluated"] == 3
    decisions = {row["decision"]: row["count"] for row in body["decision_distribution"]}
    assert decisions == {"STRONG_BUY_CANDIDATE": 1, "BUY_CANDIDATE": 1, "HOLD": 1}
    buckets = {row["bucket_label"]: row["count"] for row in body["confidence_buckets"]}
    assert buckets["80-100"] == 1  # 92.0
    assert buckets["60-80"] == 1  # 78.0
    assert buckets["40-60"] == 1  # 55.0
    risk = {row["risk_level"]: row["count"] for row in body["risk_distribution"]}
    assert risk == {"LOW": 1, "MEDIUM": 2}


def test_decision_intelligence_collapses_repeat_requests_to_the_latest_snapshot(client, session_factory, as_staff):
    """The same symbol decided twice within the window must count once,
    using only the latest snapshot -- this table is an insert-only
    request log, not a deduplicated state table."""
    now = datetime.now(timezone.utc)
    _seed_decision_v2(session_factory, "2222", "HOLD", 50.0, decision_timestamp=now - timedelta(hours=2))
    _seed_decision_v2(session_factory, "2222", "BUY_CANDIDATE", 80.0, decision_timestamp=now - timedelta(minutes=5))

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 200
    body = response.json()
    assert body["total_symbols_evaluated"] == 1
    assert body["decision_distribution"] == [{"decision": "BUY_CANDIDATE", "count": 1}]


def test_decision_intelligence_excludes_snapshots_outside_the_window(client, session_factory, as_staff):
    stale = datetime.now(timezone.utc) - timedelta(hours=200)
    _seed_decision_v2(session_factory, "2222", "BUY_CANDIDATE", 80.0, decision_timestamp=stale)

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence?within_hours=72")

    assert response.status_code == 200
    body = response.json()
    assert body["total_symbols_evaluated"] == 0
    assert body["decision_distribution"] == []


def test_decision_intelligence_top_opportunities_are_sorted_by_confidence_not_alphabetically(
    client, session_factory, as_staff
):
    _seed_decision_v2(session_factory, "9999", "BUY_CANDIDATE", 60.0)
    _seed_decision_v2(session_factory, "1111", "STRONG_BUY_CANDIDATE", 95.0)
    _seed_decision_v2(session_factory, "5555", "BUY_CANDIDATE", 80.0)
    _seed_decision_v2(session_factory, "2222", "HOLD", 99.0)  # not a buy decision -- must be excluded

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 200
    top = response.json()["top_opportunities"]
    assert [row["symbol"] for row in top] == ["1111", "5555", "9999"]
    assert [row["confidence_score"] for row in top] == [95.0, 80.0, 60.0]


def test_decision_intelligence_reports_real_rejection_reasons_from_gates(client, session_factory, as_staff):
    _seed_decision_v2(
        session_factory,
        "2222",
        "REJECT",
        20.0,
        gates=[
            {"name": "min_liquidity", "status": "FAIL", "passed": False, "detail": "low volume", "blocking": True},
            {"name": "real_data_source", "status": "PASS", "passed": True, "detail": "ok", "blocking": True},
        ],
    )
    _seed_decision_v2(
        session_factory,
        "1120",
        "INSUFFICIENT_DATA",
        10.0,
        gates=[
            {"name": "min_liquidity", "status": "FAIL", "passed": False, "detail": "low volume", "blocking": True},
            {"name": "min_candles", "status": "FAIL", "passed": False, "detail": "too few bars", "blocking": True},
        ],
    )

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 200
    body = response.json()
    reasons = {row["gate_name"]: row["fail_count"] for row in body["rejection_reason_counts"]}
    assert reasons == {"min_liquidity": 2, "min_candles": 1}
    rejected_symbols = {row["symbol"]: row["failed_gate_names"] for row in body["rejected_opportunities"]}
    assert rejected_symbols["2222"] == ["min_liquidity"]
    assert set(rejected_symbols["1120"]) == {"min_liquidity", "min_candles"}


def test_decision_intelligence_sector_ranking_reflects_real_average_confidence(client, session_factory, as_staff):
    _seed_decision_v2(session_factory, "2222", "STRONG_BUY_CANDIDATE", 90.0, sector_ar="الطاقة")
    _seed_decision_v2(session_factory, "1120", "BUY_CANDIDATE", 70.0, sector_ar="البنوك")
    _seed_decision_v2(session_factory, "1180", "HOLD", 50.0, sector_ar="البنوك")

    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 200
    ranking = {row["sector_ar"]: row for row in response.json()["sector_ranking"]}
    assert ranking["الطاقة"]["symbols_evaluated"] == 1
    assert ranking["الطاقة"]["average_confidence"] == pytest.approx(90.0)
    assert ranking["الطاقة"]["buy_candidate_count"] == 1
    assert ranking["البنوك"]["symbols_evaluated"] == 2
    assert ranking["البنوك"]["average_confidence"] == pytest.approx(60.0)
    assert ranking["البنوك"]["buy_candidate_count"] == 1
    # Must be ranked by confidence -- never alphabetically.
    ranking_order = [row["sector_ar"] for row in response.json()["sector_ranking"]]
    assert ranking_order == ["الطاقة", "البنوك"]


def test_decision_intelligence_handles_an_entirely_empty_database(client, session_factory, as_staff):
    response = client.get("/api/v1/admin/market-intelligence/decision-intelligence")

    assert response.status_code == 200
    body = response.json()
    assert body["total_symbols_evaluated"] == 0
    assert body["decision_distribution"] == []
    assert body["confidence_buckets"] == []
    assert body["risk_distribution"] == []
    assert body["top_opportunities"] == []
    assert body["rejected_opportunities"] == []
    assert body["rejection_reason_counts"] == []
    assert body["sector_ranking"] == []


# --- GET /universe-diagnostics: pagination evidence ------------------------


def test_universe_diagnostics_surfaces_real_pagination_evidence(client, session_factory, as_staff, monkeypatch):
    """Real evidence for whether the SAHMK /companies/ directory's
    ~100-instrument result is a pagination limit or the provider's
    genuine result set: the route must surface
    SahmkMarketDataService.last_directory_diagnostics (pages fetched,
    whether a next/count/total signal was ever observed, the raw
    envelope's own top-level keys) -- previously computed by the
    service but silently discarded by every caller."""
    from src.market_data import provider_factory
    from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider
    from src.market_data.sahmk.models import SahmkCompanyProfile
    from src.market_data.sahmk.service import _DirectoryDiagnostics

    provider = SahmkMarketDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")

    async def _fake_get_company_directory():
        provider._service.last_directory_diagnostics = _DirectoryDiagnostics(
            pages_fetched=1,
            total_fetched=1,
            pagination_signal=None,
            reported_total=None,
            universe_verdict="UNIVERSE_NOT_VERIFIED",
            first_page_keys=["companies"],
            first_item_keys=["symbol", "market_segment"],
            sector_populated_count=0,
            name_ar_populated_count=0,
        )
        return [
            SahmkCompanyProfile(
                symbol="2222", name="Saudi Aramco", name_ar=None, sector=None, industry=None,
                exchange=None, raw={"market_segment": "TASI", "security_type": "Equity"},
            )
        ]

    provider._service.get_company_directory = _fake_get_company_directory

    async def _fake_get_provider(force_refresh=False):
        return provider

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_provider)

    response = client.get("/api/v1/admin/market-intelligence/universe-diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["pages_fetched"] == 1
    assert body["pagination"]["pagination_signal"] is None
    assert body["pagination"]["reported_total"] is None
    assert body["pagination"]["universe_verdict"] == "UNIVERSE_NOT_VERIFIED"
    assert body["pagination"]["first_page_keys"] == ["companies"]
    assert body["pagination"]["first_item_keys"] == ["symbol", "market_segment"]


# --- GET /symbol-lookup-diagnostics: discovery-vs-data-coverage evidence ---


def test_symbol_lookup_diagnostics_reports_real_per_symbol_call_outcomes(
    client, session_factory, as_staff, monkeypatch
):
    """Real evidence for whether SAHMK's directory-discovery cap is a
    discovery-only limitation or a genuine data-coverage limitation:
    for a symbol the caller passes explicitly, the route must call the
    real per-symbol quote/company-profile/historical/fundamentals/
    dividends methods directly and report each real outcome -- success
    for one symbol, a real exception for another -- never fabricating
    either."""
    from src.market_data import fundamental_provider_factory, provider_factory
    from src.market_data.providers.sahmk_fundamental_data_provider import SahmkFundamentalDataProvider
    from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider

    market_provider = SahmkMarketDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")

    async def _fake_get_symbol_directory():
        return [{"symbol": "2222"}]

    async def _fake_get_latest_quote(symbol):
        if symbol == "9999":
            raise ValueError("SahmkRequestError: 404 not found")
        return {"symbol": symbol, "price": 42.0}

    async def _fake_get_company_profile(symbol):
        if symbol == "9999":
            raise ValueError("SahmkRequestError: 404 not found")
        return {"symbol": symbol, "name": "Example Co"}

    async def _fake_get_stock_data(symbol):
        if symbol == "9999":
            raise ValueError("SahmkRequestError: 404 not found")
        return {"symbol": symbol, "close": 42.0}

    market_provider.get_symbol_directory = _fake_get_symbol_directory
    market_provider.get_latest_quote = _fake_get_latest_quote
    market_provider.get_company_profile = _fake_get_company_profile
    market_provider.get_stock_data = _fake_get_stock_data

    fundamental_provider = SahmkFundamentalDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")

    async def _fake_get_dividends(symbol):
        if symbol == "9999":
            raise ValueError("SahmkRequestError: 404 not found")
        return []  # a real symbol that simply has no dividend history -- still "available"

    async def _fake_get_fundamentals(symbol, period_type="annual"):
        if symbol == "9999":
            raise ValueError("SahmkRequestError: 404 not found")
        return {"symbol": symbol}

    fundamental_provider.get_dividends = _fake_get_dividends
    fundamental_provider.get_fundamentals = _fake_get_fundamentals

    async def _fake_get_market_provider(force_refresh=False):
        return market_provider

    async def _fake_get_fundamental_provider(force_refresh=False):
        return fundamental_provider

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_market_provider)
    monkeypatch.setattr(fundamental_provider_factory, "get_fundamental_data_provider", _fake_get_fundamental_provider)

    response = client.get(
        "/api/v1/admin/market-intelligence/symbol-lookup-diagnostics", params={"symbols": "2222,9999"}
    )

    assert response.status_code == 200
    body = response.json()
    by_symbol = {r["symbol"]: r for r in body["results"]}

    real = by_symbol["2222"]
    assert real["in_last_known_directory"] is True
    assert real["quote"]["available"] is True
    assert real["company_profile"]["available"] is True
    assert real["historical_bar"]["available"] is True
    assert real["dividends"]["available"] is True  # empty list is still a real, available answer
    assert real["fundamentals"]["available"] is True

    missing = by_symbol["9999"]
    assert missing["in_last_known_directory"] is False
    assert missing["quote"]["available"] is False
    assert "404" in missing["quote"]["detail"]


def test_symbol_lookup_diagnostics_surfaces_real_sector_from_company_profile(
    client, session_factory, as_staff, monkeypatch
):
    """Real evidence for whether SAHMK's per-symbol company-profile
    endpoint carries sector/industry data the bulk directory doesn't:
    the route must pass the profile dict's real sector/industry values
    straight through, never fabricate or infer them."""
    from src.market_data import fundamental_provider_factory, provider_factory
    from src.market_data.providers.sahmk_fundamental_data_provider import SahmkFundamentalDataProvider
    from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider

    market_provider = SahmkMarketDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")

    async def _fake_get_symbol_directory():
        return [{"symbol": "2222"}]

    async def _fake_get_latest_quote(symbol):
        return {"symbol": symbol, "price": 42.0}

    async def _fake_get_company_profile(symbol):
        return {
            "symbol": symbol,
            "name": "Example Co",
            "sector": "Materials",
            "industry": "Chemicals",
            "exchange": "TASI",
        }

    async def _fake_get_stock_data(symbol):
        return {"symbol": symbol, "close": 42.0}

    market_provider.get_symbol_directory = _fake_get_symbol_directory
    market_provider.get_latest_quote = _fake_get_latest_quote
    market_provider.get_company_profile = _fake_get_company_profile
    market_provider.get_stock_data = _fake_get_stock_data

    fundamental_provider = SahmkFundamentalDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")

    async def _fake_get_dividends(symbol):
        return []

    async def _fake_get_fundamentals(symbol, period_type="annual"):
        return {"symbol": symbol}

    fundamental_provider.get_dividends = _fake_get_dividends
    fundamental_provider.get_fundamentals = _fake_get_fundamentals

    async def _fake_get_market_provider(force_refresh=False):
        return market_provider

    async def _fake_get_fundamental_provider(force_refresh=False):
        return fundamental_provider

    monkeypatch.setattr(provider_factory, "get_market_data_provider", _fake_get_market_provider)
    monkeypatch.setattr(fundamental_provider_factory, "get_fundamental_data_provider", _fake_get_fundamental_provider)

    response = client.get(
        "/api/v1/admin/market-intelligence/symbol-lookup-diagnostics", params={"symbols": "2222"}
    )

    assert response.status_code == 200
    body = response.json()
    profile_check = body["results"][0]["company_profile"]
    assert profile_check["raw_sector"] == "Materials"
    assert profile_check["raw_industry"] == "Chemicals"
    assert set(profile_check["raw_keys"]) >= {"sector", "industry", "name", "exchange"}

    # A quote check has no sector/industry keys at all -- must stay None,
    # never leak an unrelated value or fabricate one.
    quote_check = body["results"][0]["quote"]
    assert quote_check["raw_sector"] is None
    assert quote_check["raw_industry"] is None
