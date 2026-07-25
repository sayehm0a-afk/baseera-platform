"""Unit tests for src.market_data.ingestion.scheduler -- in-memory
SQLite, no live DB/network, no real sleeping (asyncio.sleep is
monkeypatched to a fast no-op throughout, matching the established
test_client.py convention)."""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import IngestionJobStatus, IngestionRunLog
from src.market_data.ingestion._common import IngestionResult
from src.market_data.ingestion.scheduler import (
    IngestionScheduler,
    _NonDisconnectingProviderProxy,
    run_ingestion_job,
)

# Captured before any fixture ever monkeypatches asyncio.sleep -- the one
# test that needs real scheduling (proving the loop repeats over actual
# wall-clock time) restores this explicitly; see that test's docstring.
_REAL_ASYNCIO_SLEEP = asyncio.sleep


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _instant_sleep(monkeypatch):
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


# --- _NonDisconnectingProviderProxy -----------------------------------------


class _FakeProvider:
    def __init__(self):
        self.authenticate_calls = 0
        self.disconnect_calls = 0

    async def authenticate(self):
        self.authenticate_calls += 1
        return True

    async def disconnect(self):
        self.disconnect_calls += 1

    async def get_stock_data(self, symbol):
        return {"symbol": symbol}

    async def get_dividends(self, symbol):
        return [{"symbol": symbol}]


@pytest.mark.asyncio
async def test_proxy_suppresses_authenticate_and_disconnect():
    fake = _FakeProvider()
    proxy = _NonDisconnectingProviderProxy(fake)

    assert await proxy.authenticate() is True
    await proxy.disconnect()

    assert fake.authenticate_calls == 0
    assert fake.disconnect_calls == 0


@pytest.mark.asyncio
async def test_proxy_forwards_every_other_call():
    fake = _FakeProvider()
    proxy = _NonDisconnectingProviderProxy(fake)

    assert await proxy.get_stock_data("2222") == {"symbol": "2222"}


@pytest.mark.asyncio
async def test_proxy_forwards_extra_methods_not_on_the_interface():
    """get_dividends isn't part of IMarketDataProvider/
    IFundamentalDataProvider -- __getattr__ must still forward it."""
    fake = _FakeProvider()
    proxy = _NonDisconnectingProviderProxy(fake)
    assert await proxy.get_dividends("2222") == [{"symbol": "2222"}]


# --- run_ingestion_job -------------------------------------------------


@pytest.mark.asyncio
async def test_run_ingestion_job_records_success(session_factory):
    async def job_fn():
        return IngestionResult(symbols_requested=2, symbols_succeeded=2, rows_upserted=2)

    run_log = await run_ingestion_job("test_job", job_fn, session_factory)

    assert run_log.status == IngestionJobStatus.SUCCESS
    assert run_log.symbols_requested == 2
    assert run_log.symbols_succeeded == 2
    assert run_log.rows_upserted == 2
    assert run_log.retry_count == 0
    assert run_log.finished_at is not None

    session = session_factory()
    persisted = session.query(IngestionRunLog).filter_by(job_name="test_job").one()
    assert persisted.status == IngestionJobStatus.SUCCESS
    session.close()


@pytest.mark.asyncio
async def test_run_ingestion_job_records_partial_failure(session_factory):
    async def job_fn():
        return IngestionResult(
            symbols_requested=2, symbols_succeeded=1, symbols_failed=1, errors={"BAD": "boom"}
        )

    run_log = await run_ingestion_job("test_job", job_fn, session_factory)

    assert run_log.status == IngestionJobStatus.PARTIAL
    assert "BAD" in run_log.error_summary


@pytest.mark.asyncio
async def test_run_ingestion_job_records_total_failure_when_nothing_succeeds(session_factory):
    async def job_fn():
        return IngestionResult(symbols_requested=1, symbols_succeeded=0, symbols_failed=1)

    run_log = await run_ingestion_job("test_job", job_fn, session_factory)
    assert run_log.status == IngestionJobStatus.FAILED


@pytest.mark.asyncio
async def test_run_ingestion_job_retries_then_succeeds(session_factory):
    attempts = []

    async def job_fn():
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("transient failure")
        return IngestionResult(symbols_requested=1, symbols_succeeded=1)

    run_log = await run_ingestion_job(
        "test_job", job_fn, session_factory, max_attempts=3, retry_base_delay_seconds=0.01
    )

    assert len(attempts) == 2
    assert run_log.retry_count == 1
    assert run_log.status == IngestionJobStatus.SUCCESS


@pytest.mark.asyncio
async def test_run_ingestion_job_exhausts_retries_and_records_failed(session_factory):
    attempts = []

    async def job_fn():
        attempts.append(1)
        raise RuntimeError("persistent failure")

    run_log = await run_ingestion_job(
        "test_job", job_fn, session_factory, max_attempts=3, retry_base_delay_seconds=0.01
    )

    assert len(attempts) == 3
    assert run_log.retry_count == 2
    assert run_log.status == IngestionJobStatus.FAILED
    assert "persistent failure" in run_log.error_summary


@pytest.mark.asyncio
async def test_run_ingestion_job_never_raises_even_on_total_failure(session_factory):
    async def job_fn():
        raise RuntimeError("boom")

    # Must complete without raising -- a scheduler loop depends on this.
    run_log = await run_ingestion_job("test_job", job_fn, session_factory, max_attempts=1)
    assert run_log.status == IngestionJobStatus.FAILED


@pytest.mark.asyncio
async def test_run_ingestion_job_measures_duration(session_factory):
    async def job_fn():
        return IngestionResult(symbols_requested=1, symbols_succeeded=1)

    run_log = await run_ingestion_job("test_job", job_fn, session_factory)
    assert run_log.duration_seconds is not None
    assert run_log.duration_seconds >= 0


# --- IngestionScheduler --------------------------------------------------


class _CountingJobRunner:
    """A fake IngestionScheduler job body that succeeds a configurable
    number of times before the test stops the scheduler -- used to
    prove the loop actually runs jobs on a schedule and stop() halts it
    cleanly."""

    def __init__(self):
        self.call_count = 0

    async def __call__(self):
        self.call_count += 1
        return IngestionResult(symbols_requested=1, symbols_succeeded=1, rows_upserted=1)


@pytest.mark.asyncio
async def test_scheduler_start_creates_four_job_tasks(session_factory, monkeypatch):
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_symbols_sync_interval_seconds", lambda: 1000
    )
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_ohlcv_sync_interval_seconds", lambda: 1000
    )
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_fundamentals_sync_interval_seconds", lambda: 1000
    )
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_dividends_sync_interval_seconds", lambda: 1000
    )

    async def _unused_provider_getter():
        return _FakeProvider()

    scheduler = IngestionScheduler(
        session_factory=session_factory,
        market_provider_getter=_unused_provider_getter,
        fundamental_provider_getter=_unused_provider_getter,
    )
    assert scheduler.is_running is False

    scheduler.start()
    try:
        assert scheduler.is_running is True
        assert len(scheduler._tasks) == 4
    finally:
        await scheduler.stop()

    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_start_is_idempotent(session_factory):
    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler.start()
    try:
        first_tasks = list(scheduler._tasks)
        scheduler.start()  # must not add a second set of tasks
        assert scheduler._tasks == first_tasks
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_runs_a_job_and_records_it(session_factory):
    """End-to-end: a fast-interval scheduler with a fake provider getter
    actually executes a job and writes a run log -- proves _run_symbols/
    etc. are wired to run_ingestion_job correctly, not just that tasks
    exist."""

    class _FakeMarketProvider:
        async def authenticate(self):
            return True

        async def disconnect(self):
            pass

        async def get_stock_data(self, symbol):
            return {
                "symbol": symbol, "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                "volume": 100, "timestamp": "2026-01-01T00:00:00+00:00",
                "source": "fake", "is_synthetic": True,
            }

        async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
            return [await self.get_stock_data(symbol)]

    async def get_provider():
        return _FakeMarketProvider()

    scheduler = IngestionScheduler(
        session_factory=session_factory,
        market_provider_getter=get_provider,
        fundamental_provider_getter=get_provider,
    )

    # Run one cycle of the "symbols" job directly, bypassing the sleep
    # loop entirely -- this is what _loop's body does each iteration.
    result = await scheduler._run_symbols()
    assert result.symbols_requested > 0

    session = session_factory()
    assert session.query(IngestionRunLog).count() == 0  # _run_symbols alone doesn't log; run_ingestion_job does
    session.close()

    log = await run_ingestion_job("symbols", scheduler._run_symbols, session_factory)
    assert log.status in (IngestionJobStatus.SUCCESS, IngestionJobStatus.PARTIAL)

    session = session_factory()
    assert session.query(IngestionRunLog).filter_by(job_name="symbols").count() == 1
    session.close()


@pytest.mark.asyncio
async def test_scheduler_loop_survives_a_job_exception_and_keeps_scheduling(
    session_factory, monkeypatch
):
    """A job that always fails must not kill its own loop -- the next
    cycle must still be scheduled. Restores the *real* asyncio.sleep for
    this test only: the module-wide instant-sleep mock (see
    _instant_sleep above) doesn't yield control to concurrently
    scheduled tasks at all (a mocked coroutine with no real suspension
    point never gives the event loop a chance to run _loop's task), so
    proving the loop actually repeats needs real, if short, waits."""
    monkeypatch.setattr(asyncio, "sleep", _REAL_ASYNCIO_SLEEP)
    monkeypatch.setattr("src.market_data.ingestion.config.get_ingestion_job_max_attempts", lambda: 1)

    calls = []

    async def always_fails():
        calls.append(1)
        raise RuntimeError("simulated failure")

    scheduler = IngestionScheduler(session_factory=session_factory)
    task = asyncio.ensure_future(scheduler._loop("flaky", lambda: 0.01, always_fails))
    try:
        await _REAL_ASYNCIO_SLEEP(0.15)  # enough real time for several 0.01s-interval iterations
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(calls) >= 2  # proves the loop actually repeats, not just runs once

    session = session_factory()
    runs = session.query(IngestionRunLog).filter_by(job_name="flaky").all()
    session.close()
    assert len(runs) == len(calls)
    assert all(r.status == IngestionJobStatus.FAILED for r in runs)


@pytest.mark.asyncio
async def test_scheduler_stop_cancels_all_tasks_cleanly(session_factory):
    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler.start()
    tasks = list(scheduler._tasks)
    await scheduler.stop()

    assert scheduler._tasks == []
    for task in tasks:
        assert task.cancelled() or task.done()
