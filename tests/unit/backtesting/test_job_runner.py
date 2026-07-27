"""Unit tests for src.backtesting.job_runner.run_backtest_job --
in-memory SQLite (StaticPool, so every session_factory() call shares
the same in-memory database, the same pattern
tests/integration/api/conftest.py already established), no live
network, no real sleeping (asyncio.sleep monkeypatched to a fast
no-op, matching the ingestion scheduler test convention).
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backtesting.job_runner import run_backtest_job
from src.core.db.database import Base
from src.domain.models import (
    BacktestRun,
    BacktestRunStatus,
    CalibrationConfig,
    CalibrationStatus,
    DataProvenanceMode,
    PriceBar,
    RecommendationSnapshot,
    Stock,
    Timeframe,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _instant_sleep(monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


def _seed_bars(session_factory, symbol="2222", count=200):
    session = session_factory()
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        price = 30.0 + i * 0.1
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(price)), high=Decimal(str(price + 0.2)), low=Decimal(str(price - 0.2)),
                close=Decimal(str(price)), volume=1000 + i, source="dev-synthetic", is_synthetic=True,
            )
        )
    session.commit()
    session.close()


def _make_run(session_factory, **overrides):
    session = session_factory()
    defaults = dict(
        idempotency_key="k1", status=BacktestRunStatus.PENDING, symbols=["2222"],
        data_provenance_mode=DataProvenanceMode.SYNTHETIC, strategy="buy_and_hold",
        start_date=date(2026, 2, 1), end_date=date(2026, 5, 1), evaluation_frequency_days=14,
        holding_horizon_days=20, target_price_horizon_days=30,
    )
    defaults.update(overrides)
    run = BacktestRun(**defaults)
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()
    return run_id


def _fetch(session_factory, run_id):
    session = session_factory()
    run = session.query(BacktestRun).filter_by(id=run_id).one()
    session.expunge(run)
    session.close()
    return run


# --- happy path -----------------------------------------------------


@pytest.mark.asyncio
async def test_successful_run_completes_with_metrics(session_factory):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory)

    await run_backtest_job(run_id, session_factory)

    run = _fetch(session_factory, run_id)
    assert run.status == BacktestRunStatus.SUCCESS
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.duration_seconds is not None
    assert run.metrics is not None
    assert "overall" in run.metrics
    # progress_current lands on evaluated_count, not progress_total, whenever
    # some scheduled evaluation dates were skipped (e.g. too little price
    # history yet) -- both are legitimate, self-consistent outcomes.
    assert run.progress_current == run.metrics["evaluated_count"]
    assert run.progress_current > 0
    assert run.progress_total > 0


@pytest.mark.asyncio
async def test_successful_run_persists_recommendation_snapshots(session_factory):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory)

    await run_backtest_job(run_id, session_factory)

    session = session_factory()
    count = session.query(RecommendationSnapshot).filter_by(run_id=run_id).count()
    session.close()
    assert count > 0


# --- calibration wiring --------------------------------------------


@pytest.mark.asyncio
async def test_run_with_calibration_version_uses_that_configuration(session_factory):
    _seed_bars(session_factory)
    session = session_factory()
    session.add(
        CalibrationConfig(
            version="cal-1", status=CalibrationStatus.ACTIVE,
            config={"recommendation_tuning": {"buy_threshold": 58.0}},
        )
    )
    session.commit()
    session.close()

    run_id = _make_run(session_factory, strategy="ai_decision_engine", calibration_version="cal-1")
    await run_backtest_job(run_id, session_factory)

    run = _fetch(session_factory, run_id)
    assert run.status == BacktestRunStatus.SUCCESS


@pytest.mark.asyncio
async def test_run_with_unknown_calibration_version_fails_without_retry(session_factory):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory, calibration_version="does-not-exist")

    await run_backtest_job(run_id, session_factory)

    run = _fetch(session_factory, run_id)
    assert run.status == BacktestRunStatus.FAILED
    assert "does-not-exist" in run.error_message or "ValueError" in run.error_message


# --- transient vs non-transient failure handling --------------------


@pytest.mark.asyncio
async def test_transient_failure_is_retried_then_succeeds(session_factory, monkeypatch):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory)

    calls = {"n": 0}
    import src.backtesting.job_runner as job_runner_module

    real_execute = job_runner_module._execute_sync

    def flaky_execute(session, rid):
        calls["n"] += 1
        if calls["n"] < 2:
            raise OperationalError("select 1", {}, Exception("connection reset"))
        return real_execute(session, rid)

    monkeypatch.setattr(job_runner_module, "_execute_sync", flaky_execute)

    await run_backtest_job(run_id, session_factory, max_attempts=3, retry_base_delay_seconds=0.01)

    run = _fetch(session_factory, run_id)
    assert calls["n"] == 2
    assert run.status == BacktestRunStatus.SUCCESS


@pytest.mark.asyncio
async def test_transient_failure_exhausts_retries_and_records_failed(session_factory, monkeypatch):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory)

    import src.backtesting.job_runner as job_runner_module

    def always_flaky(session, rid):
        raise OperationalError("select 1", {}, Exception("connection reset"))

    monkeypatch.setattr(job_runner_module, "_execute_sync", always_flaky)

    await run_backtest_job(run_id, session_factory, max_attempts=2, retry_base_delay_seconds=0.01)

    run = _fetch(session_factory, run_id)
    assert run.status == BacktestRunStatus.FAILED
    assert "OperationalError" in run.error_message


@pytest.mark.asyncio
async def test_non_transient_failure_is_not_retried(session_factory, monkeypatch):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory)

    calls = {"n": 0}
    import src.backtesting.job_runner as job_runner_module

    def broken_execute(session, rid):
        calls["n"] += 1
        raise ValueError("boom -- a configuration bug, not a transient failure")

    monkeypatch.setattr(job_runner_module, "_execute_sync", broken_execute)

    await run_backtest_job(run_id, session_factory, max_attempts=3, retry_base_delay_seconds=0.01)

    run = _fetch(session_factory, run_id)
    assert calls["n"] == 1  # never retried
    assert run.status == BacktestRunStatus.FAILED
    assert "boom" in run.error_message


# --- cancellation --------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_requested_before_start_yields_cancelled_status(session_factory):
    _seed_bars(session_factory, count=400)
    run_id = _make_run(
        session_factory, end_date=date(2027, 1, 1), evaluation_frequency_days=3, cancel_requested=True
    )

    await run_backtest_job(run_id, session_factory)

    run = _fetch(session_factory, run_id)
    assert run.status == BacktestRunStatus.CANCELLED


# --- idempotency ------------------------------------------------------


@pytest.mark.asyncio
async def test_rerunning_the_same_run_id_does_not_duplicate_snapshots(session_factory):
    _seed_bars(session_factory)
    run_id = _make_run(session_factory)

    await run_backtest_job(run_id, session_factory)
    session = session_factory()
    first_count = session.query(RecommendationSnapshot).filter_by(run_id=run_id).count()
    session.close()

    # Reset to PENDING and re-run, simulating a retried/resumed job.
    session = session_factory()
    session.query(BacktestRun).filter_by(id=run_id).update({"status": BacktestRunStatus.PENDING})
    session.commit()
    session.close()

    await run_backtest_job(run_id, session_factory)
    session = session_factory()
    second_count = session.query(RecommendationSnapshot).filter_by(run_id=run_id).count()
    session.close()

    assert first_count == second_count
    assert first_count > 0
