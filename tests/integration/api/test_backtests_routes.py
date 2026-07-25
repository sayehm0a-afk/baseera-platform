"""Integration tests for /api/v1/backtests/* -- real FastAPI routing,
a real BacktestingEngine run (buy_and_hold/sma_crossover strategies
against real seeded PriceBar data), in-memory SQLite.

Two things need monkeypatching, not just app.dependency_overrides:
the route handlers use Depends(get_db) (overridable normally), but
the background job (src.backtesting.job_runner.run_backtest_job) gets
its session factory via a *local* `from src.core.db.database import
get_session_factory` call inside create_backtest() -- the same
gotcha test_ingestion_status.py already documents -- so
database.get_session_factory itself must be monkeypatched too.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.core.db import database
from src.core.db.database import Base, get_db
from src.domain.models import PriceBar, Stock, Timeframe


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
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


def _seed_bars(session_factory, symbol="2222", count=300, sector="Energy", source="dev-synthetic", is_synthetic=True):
    session = session_factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 30.0
    for i in range(count):
        price += 0.05
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(round(price, 4))), high=Decimal(str(round(price + 0.2, 4))),
                low=Decimal(str(round(price - 0.2, 4))), close=Decimal(str(round(price, 4))),
                volume=1000 + i, source=source, is_synthetic=is_synthetic,
            )
        )
    session.commit()
    session.close()


_VALID_REQUEST = {
    "symbols": ["2222"], "start_date": "2026-02-01", "end_date": "2026-08-01",
    "data_provenance_mode": "SYNTHETIC", "strategy": "buy_and_hold", "evaluation_frequency_days": 14,
}


# --- create + idempotency -----------------------------------------------


def test_create_backtest_runs_to_completion(client, session_factory):
    _seed_bars(session_factory)
    response = client.post("/api/v1/backtests", json=_VALID_REQUEST)
    assert response.status_code == 200
    run_id = response.json()["id"]

    status = client.get(f"/api/v1/backtests/{run_id}/status").json()
    assert status["status"] == "SUCCESS"
    assert status["progress_current"] > 0
    assert status["duration_seconds"] is not None


def test_resubmitting_the_identical_request_returns_the_same_run(client, session_factory):
    _seed_bars(session_factory)
    first = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()
    second = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()
    assert first["id"] == second["id"]
    assert first["idempotency_key"] == second["idempotency_key"]


def test_a_different_request_creates_a_different_run(client, session_factory):
    _seed_bars(session_factory)
    first = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()
    other = dict(_VALID_REQUEST, strategy="sma_crossover")
    second = client.post("/api/v1/backtests", json=other).json()
    assert first["id"] != second["id"]


def test_duplicate_full_market_backtest_is_rejected(client, session_factory, monkeypatch):
    monkeypatch.setenv("BACKTEST_FULL_MARKET_SYMBOL_THRESHOLD", "2")
    symbols = ["2222", "1120"]
    for symbol in symbols:
        _seed_bars(session_factory, symbol=symbol)

    # Manually insert a RUNNING large-scope run to simulate one already in flight.
    from src.domain.models import BacktestRun, BacktestRunStatus, DataProvenanceMode

    session = session_factory()
    session.add(
        BacktestRun(
            idempotency_key="already-running", status=BacktestRunStatus.RUNNING, symbols=symbols,
            data_provenance_mode=DataProvenanceMode.SYNTHETIC, start_date=date(2026, 1, 1), end_date=date(2026, 2, 1),
        )
    )
    session.commit()
    session.close()

    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, symbols=symbols))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_backtest"


# --- validation -----------------------------------------------------


def test_end_date_before_start_date_is_422(client, session_factory):
    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, start_date="2026-08-01", end_date="2026-02-01"))
    assert response.status_code == 422


def test_unknown_strategy_is_422(client, session_factory):
    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, strategy="not_a_real_strategy"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_backtest_config"


def test_empty_symbols_is_422(client, session_factory):
    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, symbols=[]))
    assert response.status_code == 422


def test_too_many_symbols_is_422(client, session_factory, monkeypatch):
    monkeypatch.setenv("BACKTEST_MAX_SYMBOLS", "2")
    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, symbols=["1", "2", "3"]))
    assert response.status_code == 422


def test_date_range_too_wide_is_422(client, session_factory, monkeypatch):
    monkeypatch.setenv("BACKTEST_MAX_RANGE_DAYS", "30")
    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, start_date="2026-01-01", end_date="2026-06-01"))
    assert response.status_code == 422


# --- reads: status/metrics/trades/confidence-calibration/comparison --------


def test_get_backtest_404_for_unknown_run(client, session_factory):
    response = client.get("/api/v1/backtests/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "backtest_run_not_found"


def test_metrics_endpoint_returns_the_full_report(client, session_factory):
    _seed_bars(session_factory)
    run_id = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()["id"]
    metrics = client.get(f"/api/v1/backtests/{run_id}/metrics").json()
    assert metrics["status"] == "SUCCESS"
    assert metrics["data_provenance_mode"] == "SYNTHETIC"
    assert "overall" in metrics["metrics"]
    assert "by_symbol" in metrics["metrics"]


def test_trades_endpoint_returns_persisted_snapshots(client, session_factory):
    _seed_bars(session_factory)
    run_id = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()["id"]
    trades = client.get(f"/api/v1/backtests/{run_id}/trades").json()
    assert trades["total"] > 0
    assert len(trades["trades"]) == trades["total"]  # under the default page size
    first = trades["trades"][0]
    assert first["symbol"] == "2222"
    assert first["price_bar_source"] == "dev-synthetic"
    assert first["price_bar_is_synthetic"] is True
    assert first["engine_version"]


def test_trades_endpoint_pagination(client, session_factory):
    _seed_bars(session_factory)
    run_id = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()["id"]
    total = client.get(f"/api/v1/backtests/{run_id}/trades").json()["total"]
    assert total > 1

    page = client.get(f"/api/v1/backtests/{run_id}/trades", params={"limit": 1, "offset": 0}).json()
    assert len(page["trades"]) == 1
    page2 = client.get(f"/api/v1/backtests/{run_id}/trades", params={"limit": 1, "offset": 1}).json()
    assert page2["trades"][0]["id"] != page["trades"][0]["id"]


def test_confidence_calibration_endpoint(client, session_factory):
    _seed_bars(session_factory)
    run_id = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()["id"]
    calibration = client.get(f"/api/v1/backtests/{run_id}/confidence-calibration").json()
    assert calibration["id"] == run_id
    # buy_and_hold always reports confidence=100 -> a single bucket.
    assert calibration["overall_error"] is not None
    assert len(calibration["buckets"]) >= 1


def test_comparison_endpoint_finds_matching_completed_runs(client, session_factory):
    _seed_bars(session_factory)
    first = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()
    client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, strategy="sma_crossover"))

    comparison = client.get(f"/api/v1/backtests/{first['id']}/comparison").json()
    strategies = {c["strategy"] for c in comparison["comparisons"]}
    assert strategies == {"buy_and_hold", "sma_crossover"}


def test_comparison_endpoint_excludes_different_scope_runs(client, session_factory):
    _seed_bars(session_factory)
    first = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()
    client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, strategy="rsi_only", end_date="2026-09-01"))

    comparison = client.get(f"/api/v1/backtests/{first['id']}/comparison").json()
    strategies = {c["strategy"] for c in comparison["comparisons"]}
    assert "rsi_only" not in strategies  # different end_date -> different scope


# --- cancel -----------------------------------------------------------


def test_cancel_on_a_finished_run_is_a_no_op(client, session_factory):
    _seed_bars(session_factory)
    run_id = client.post("/api/v1/backtests", json=_VALID_REQUEST).json()["id"]
    response = client.post(f"/api/v1/backtests/{run_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"  # unchanged, not cancelled retroactively


def test_cancel_404_for_unknown_run(client, session_factory):
    response = client.post("/api/v1/backtests/999999/cancel")
    assert response.status_code == 404


# --- provenance -------------------------------------------------------


def test_live_provenance_mode_runs_against_live_labeled_bars(client, session_factory):
    _seed_bars(session_factory, source="sahmk", is_synthetic=False)
    response = client.post("/api/v1/backtests", json=dict(_VALID_REQUEST, data_provenance_mode="LIVE"))
    run_id = response.json()["id"]
    status = client.get(f"/api/v1/backtests/{run_id}/status").json()
    assert status["status"] == "SUCCESS"

    trades = client.get(f"/api/v1/backtests/{run_id}/trades").json()
    assert trades["total"] > 0
    assert all(t["price_bar_is_synthetic"] is False for t in trades["trades"])
