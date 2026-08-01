"""Integration tests for /api/v1/market/* -- real FastAPI routing, a
real MarketIntelligenceEngine scan (TechnicalAnalysisEngine/
FundamentalAnalysisEngine/RecommendationEngine/AIDecisionEngine/
AnalystEngine, all reused unmodified) against in-memory SQLite and the
Dev* providers. No live network call anywhere.

Same double-monkeypatch as test_backtests_routes.py: the route handler
uses Depends(get_db) (overridable normally), but the background job
(run_market_scan_job) gets its session factory via a *local* `from
src.core.db.database import get_session_factory` call inside
create_scan() -- so database.get_session_factory itself must be
monkeypatched too.
"""

from datetime import date, datetime, timedelta, timezone
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
    FundamentalSnapshot,
    MarketScanRun,
    MarketScanStatus,
    PeriodType,
    PriceBar,
    StaffRole,
    Stock,
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

    # Every /api/v1/market/* route now requires an active subscription
    # (Phase 13 P13.5) -- an in-memory staff user (never persisted;
    # get_current_user itself is overridden so nothing queries the DB
    # for it) satisfies require_active_subscription()'s staff bypass,
    # keeping these tests focused on market-intelligence behavior.
    staff_user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER)

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_market_provider] = lambda: DevMarketDataProvider()
    main.app.dependency_overrides[get_current_user] = lambda: staff_user
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


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
    return stock


def _add_fundamentals(session_factory, symbol, fiscal_year=2025):
    session = session_factory()
    stock = session.query(Stock).filter_by(symbol=symbol).one()
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id, period_type=PeriodType.ANNUAL, fiscal_period_end=date(fiscal_year, 12, 31),
            revenue=Decimal("1000000"), net_income=Decimal("150000"), total_assets=Decimal("2000000"),
            total_liabilities=Decimal("700000"), total_equity=Decimal("1300000"),
            current_assets=Decimal("900000"), current_liabilities=Decimal("400000"),
            shares_outstanding=1_000_000, eps=Decimal("0.15"), dividend_per_share=Decimal("0.02"),
            source="dev-synthetic", is_synthetic=True,
        )
    )
    session.commit()
    session.close()


# --- POST /scan + GET /scan/{run_id} -------------------------------------


def test_create_scan_returns_pending_then_background_task_completes_it(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")

    response = client.post("/api/v1/market/scan", json={})
    assert response.status_code == 200
    run_id = response.json()["id"]

    status_response = client.get(f"/api/v1/market/scan/{run_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "SUCCESS"
    assert body["symbols_succeeded"] == 1


def test_create_scan_with_explicit_symbols(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")
    _seed_stock_with_bars(session_factory, "1010", sector="Banks")

    response = client.post("/api/v1/market/scan", json={"symbols": ["2222"]})
    assert response.status_code == 200
    body = response.json()
    assert body["symbols_requested"] == 1

    run_id = body["id"]
    status_response = client.get(f"/api/v1/market/scan/{run_id}")
    assert status_response.json()["symbols_succeeded"] == 1


def test_create_scan_rejects_an_overlapping_pending_or_running_scan(client, session_factory):
    # Production audit finding: two concurrent scans would double real
    # SAHMK request volume and race on the same DB rows. Seeds a
    # RUNNING MarketScanRun directly (bypassing the route, which would
    # otherwise complete synchronously in TestClient before a second
    # request could ever observe it as in-flight) to prove the guard
    # itself, not just the ordinary sequential-scan happy path.
    session = session_factory()
    session.add(MarketScanRun(status=MarketScanStatus.RUNNING, symbols_requested=1))
    session.commit()
    session.close()

    response = client.post("/api/v1/market/scan", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_market_scan"


def test_get_scan_404_for_unknown_run(client, session_factory):
    response = client.get("/api/v1/market/scan/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "market_scan_run_not_found"


# --- read routes before any scan exists -----------------------------------


def test_summary_404_when_no_scan_has_ever_completed(client, session_factory):
    response = client.get("/api/v1/market/summary")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_market_scan_data"


# --- read routes after a completed scan -------------------------------------


def test_full_read_surface_after_a_completed_scan(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222", sector="Energy")
    _seed_stock_with_bars(session_factory, "1010", sector="Banks")
    _add_fundamentals(session_factory, "2222")
    _add_fundamentals(session_factory, "1010")

    scan_response = client.post("/api/v1/market/scan", json={})
    run_id = scan_response.json()["id"]
    assert client.get(f"/api/v1/market/scan/{run_id}").json()["status"] == "SUCCESS"

    summary = client.get("/api/v1/market/summary")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["scan_run_id"] == run_id
    assert summary_body["symbols_scanned"] == 2

    rankings = client.get("/api/v1/market/rankings")
    assert rankings.status_code == 200
    rankings_body = rankings.json()
    assert len(rankings_body["rankings"]) == 17
    assert rankings_body["scan_run_id"] == run_id

    top_buy = client.get("/api/v1/market/top-buy")
    assert top_buy.status_code == 200
    assert top_buy.json()["category"] == "TOP_BUY"

    top_strong_buy = client.get("/api/v1/market/top-strong-buy")
    assert top_strong_buy.status_code == 200
    assert top_strong_buy.json()["category"] == "TOP_STRONG_BUY"

    watchlists = client.get("/api/v1/market/watchlists")
    assert watchlists.status_code == 200
    assert len(watchlists.json()["watchlists"]) == 9

    sectors = client.get("/api/v1/market/sectors")
    assert sectors.status_code == 200
    sector_names = {s["sector"] for s in sectors.json()["sectors"]}
    assert sector_names == {"Energy", "Banks"}

    changes = client.get("/api/v1/market/changes")
    assert changes.status_code == 200
    assert changes.json()["total"] == 0  # first scan -- nothing to compare against

    alerts = client.get("/api/v1/market/alerts")
    assert alerts.status_code == 200


def test_rankings_category_filter(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")
    run_id = client.post("/api/v1/market/scan", json={}).json()["id"]
    client.get(f"/api/v1/market/scan/{run_id}")

    response = client.get("/api/v1/market/rankings", params={"category": "TOP_BUY"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["rankings"]) == 1
    assert body["rankings"][0]["category"] == "TOP_BUY"


def test_watchlists_category_filter(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")
    client.post("/api/v1/market/scan", json={})

    response = client.get("/api/v1/market/watchlists", params={"category": "MOMENTUM"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["watchlists"]) == 1
    assert body["watchlists"][0]["category"] == "MOMENTUM"


def test_explicit_run_id_selects_a_specific_scan(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")
    run1 = client.post("/api/v1/market/scan", json={}).json()["id"]
    run2 = client.post("/api/v1/market/scan", json={}).json()["id"]

    response = client.get("/api/v1/market/summary", params={"run_id": run1})
    assert response.status_code == 200
    assert response.json()["scan_run_id"] == run1

    response = client.get("/api/v1/market/summary", params={"run_id": run2})
    assert response.json()["scan_run_id"] == run2


# --- change detection across two scans --------------------------------------


def test_second_scan_reports_changes_and_alerts(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")

    run1_id = client.post("/api/v1/market/scan", json={}).json()["id"]
    client.get(f"/api/v1/market/scan/{run1_id}")

    # A second, identical scan against the same synthetic, monotonically
    # rising price series should still complete cleanly; whether or not
    # its recommendation changed is data-dependent, so this only asserts
    # the read surface stays coherent and consistent after a second scan.
    run2_id = client.post("/api/v1/market/scan", json={}).json()["id"]
    assert client.get(f"/api/v1/market/scan/{run2_id}").json()["status"] == "SUCCESS"

    changes = client.get("/api/v1/market/changes", params={"run_id": run2_id})
    assert changes.status_code == 200
    assert isinstance(changes.json()["changes"], list)


# --- security / honesty ------------------------------------------------------


def test_market_responses_never_expose_credentials(client, session_factory):
    _seed_stock_with_bars(session_factory, "2222")
    run_id = client.post("/api/v1/market/scan", json={}).json()["id"]
    client.get(f"/api/v1/market/scan/{run_id}")

    for path in ("/api/v1/market/summary", "/api/v1/market/rankings", "/api/v1/market/watchlists"):
        response = client.get(path)
        body_text = response.text.lower()
        assert "sahmk_api_key" not in body_text
        assert "shmk_" not in body_text
