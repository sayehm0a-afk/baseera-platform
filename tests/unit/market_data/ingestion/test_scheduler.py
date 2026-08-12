"""Unit tests for src.market_data.ingestion.scheduler -- in-memory
SQLite, no live DB/network, no real sleeping (asyncio.sleep is
monkeypatched to a fast no-op throughout, matching the established
test_client.py convention)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import IngestionJobStatus, IngestionRunLog, Stock
from src.market_data.ingestion._common import IngestionResult
from src.market_data.ingestion.scheduler import (
    _QUOTA_RETRY_SAFETY_BUFFER,
    IngestionScheduler,
    _NonDisconnectingProviderProxy,
    _compute_quota_retry_at,
    _find_quota_exceeded_cause,
    reap_stale_ingestion_runs,
    run_ingestion_job,
)
from src.market_data.sahmk.rate_limiter import (
    SahmkQuotaReservedForCriticalError,
    SahmkUpstreamQuotaExhaustedError,
)
from src.market_data.strict_mode import StrictRealDataUnavailableError

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
async def test_run_ingestion_job_records_zero_progress_summary(session_factory):
    async def job_fn():
        return IngestionResult(
            symbols_requested=1, symbols_succeeded=1, zero_progress={"9999": "no bars returned"}
        )

    run_log = await run_ingestion_job("test_job", job_fn, session_factory)

    assert run_log.status == IngestionJobStatus.SUCCESS  # zero_progress alone isn't a failure
    assert "9999" in run_log.zero_progress_summary
    assert "no bars returned" in run_log.zero_progress_summary


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


# --- _resolve_target_symbols (root-cause fix: OHLCV/fundamentals/ ------
# dividends must scale to every discovered active Stock, not stay
# capped at the static INGESTION_SYMBOL_UNIVERSE seed list forever) ----


def test_resolve_target_symbols_falls_back_to_configured_list_on_cold_start(
    session_factory, monkeypatch
):
    """Empty Stock table (no symbols job has run yet, or auto-discovery
    is off) -- must return exactly the configured seed list, unchanged
    from prior behavior."""
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_ingestion_symbol_universe",
        lambda: ["2222", "1120"],
    )
    scheduler = IngestionScheduler(session_factory=session_factory)
    assert scheduler._resolve_target_symbols() == ["2222", "1120"]


def test_resolve_target_symbols_unions_configured_with_discovered_active_stocks(
    session_factory, monkeypatch
):
    """The confirmed production root cause: once the symbols job has
    discovered and activated real Tadawul equities beyond the 5-symbol
    default, OHLCV/fundamentals/dividends must pick every one of them
    up automatically -- not silently stay capped at the seed list
    forever, which was why production only ever surfaced a handful of
    stocks."""
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_ingestion_symbol_universe",
        lambda: ["2222"],
    )
    session = session_factory()
    session.add(Stock(symbol="2222", name_en="Saudi Aramco", is_active=True))
    session.add(Stock(symbol="1120", name_en="Al Rajhi Bank", is_active=True))
    session.add(Stock(symbol="4342", name_en="Some REIT Fund", is_active=False))
    session.commit()
    session.close()

    scheduler = IngestionScheduler(session_factory=session_factory)
    resolved = scheduler._resolve_target_symbols()

    assert set(resolved) == {"2222", "1120"}  # the inactive REIT is excluded
    assert resolved.count("2222") == 1  # deduped, not doubled


@pytest.mark.asyncio
async def test_ohlcv_fundamentals_dividends_jobs_use_resolved_symbols_not_just_configured(
    session_factory, monkeypatch
):
    """End-to-end proof at the job level: a symbol discovered and
    activated by a prior symbols-job run (never in
    INGESTION_SYMBOL_UNIVERSE) must actually be ingested by the OHLCV
    job, not silently skipped."""
    monkeypatch.setattr(
        "src.market_data.ingestion.config.get_ingestion_symbol_universe",
        lambda: ["2222"],
    )
    session = session_factory()
    session.add(Stock(symbol="2222", name_en="Saudi Aramco", is_active=True))
    session.add(Stock(symbol="1211", name_en="Newly Discovered Co", is_active=True))
    session.commit()
    session.close()

    class _FakeMarketProvider:
        async def authenticate(self):
            return True

        async def disconnect(self):
            pass

        async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
            return [
                {
                    "symbol": symbol, "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                    "volume": 100, "timestamp": "2026-01-01T00:00:00+00:00",
                    "source": "fake", "is_synthetic": True,
                }
            ]

    async def get_provider():
        return _FakeMarketProvider()

    scheduler = IngestionScheduler(session_factory=session_factory, market_provider_getter=get_provider)
    result = await scheduler._run_historical_ohlcv()

    assert result.symbols_requested == 2
    assert result.symbols_succeeded == 2


@pytest.mark.asyncio
async def test_scheduler_start_reaps_a_stale_running_job_before_scheduling(session_factory):
    """Mirrors the identical fix on MarketIntelligenceScheduler: a
    process kill leaves an IngestionRunLog row stuck RUNNING forever,
    which would otherwise permanently block POST /full-discovery's
    in-flight guard after a crash -- start() must reap it."""
    session = session_factory()
    stale = IngestionRunLog(
        job_name="symbols",
        started_at=datetime.now(timezone.utc) - timedelta(hours=100),
        status=IngestionJobStatus.RUNNING,
    )
    session.add(stale)
    session.commit()
    stale_id = stale.id
    session.close()

    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler.start()
    try:
        pass
    finally:
        await scheduler.stop()

    session = session_factory()
    reaped = session.query(IngestionRunLog).filter_by(id=stale_id).one()
    assert reaped.status == IngestionJobStatus.FAILED
    session.close()


@pytest.mark.asyncio
async def test_scheduler_stop_cancels_all_tasks_cleanly(session_factory):
    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler.start()
    tasks = list(scheduler._tasks)
    await scheduler.stop()

    assert scheduler._tasks == []
    for task in tasks:
        assert task.cancelled() or task.done()


# --- run_all_jobs_once ---------------------------------------------------


@pytest.mark.asyncio
async def test_run_all_jobs_once_runs_all_four_jobs_in_dependency_order(session_factory):
    """The manual full-discovery admin route calls this -- symbols must
    run (and be recorded) before the other three, since they resolve
    their target list from Stock rows the symbols job may have just
    discovered."""
    call_order = []

    async def _make_job(name):
        async def _job():
            call_order.append(name)
            return IngestionResult(symbols_requested=1, symbols_succeeded=1)

        return _job

    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler._run_symbols = await _make_job("symbols")
    scheduler._run_historical_ohlcv = await _make_job("historical_ohlcv")
    scheduler._run_fundamentals = await _make_job("fundamentals")
    scheduler._run_dividends = await _make_job("dividends")

    run_logs = await scheduler.run_all_jobs_once()

    assert call_order == ["symbols", "historical_ohlcv", "fundamentals", "dividends"]
    assert [log.job_name for log in run_logs] == ["symbols", "historical_ohlcv", "fundamentals", "dividends"]
    assert all(log.status == IngestionJobStatus.SUCCESS for log in run_logs)

    session = session_factory()
    assert session.query(IngestionRunLog).count() == 4
    session.close()


@pytest.mark.asyncio
async def test_run_all_jobs_once_records_a_failed_job_but_still_runs_the_rest(session_factory):
    """A job that fails every retry attempt must not stop the other
    three from running -- matches run_ingestion_job's own "never
    raises" contract."""
    call_order = []

    async def _failing_symbols():
        call_order.append("symbols")
        raise RuntimeError("SAHMK directory unavailable")

    async def _make_ok_job(name):
        async def _job():
            call_order.append(name)
            return IngestionResult(symbols_requested=1, symbols_succeeded=1)

        return _job

    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler._run_symbols = _failing_symbols
    scheduler._run_historical_ohlcv = await _make_ok_job("historical_ohlcv")
    scheduler._run_fundamentals = await _make_ok_job("fundamentals")
    scheduler._run_dividends = await _make_ok_job("dividends")

    run_logs = await scheduler.run_all_jobs_once()

    assert [log.job_name for log in run_logs] == ["symbols", "historical_ohlcv", "fundamentals", "dividends"]
    assert run_logs[0].status == IngestionJobStatus.FAILED
    assert all(log.status == IngestionJobStatus.SUCCESS for log in run_logs[1:])
    # symbols was retried up to the configured max, then the other three ran once each
    assert call_order.count("symbols") >= 1
    assert call_order[-3:] == ["historical_ohlcv", "fundamentals", "dividends"]


def test_reap_stale_ingestion_runs_marks_an_old_running_row_as_failed(session_factory):
    """Production found a 'symbols' IngestionRunLog row stuck RUNNING
    for 4+ days (a container restart mid-run) -- permanently blocking
    POST /full-discovery's in-flight guard, which matches on
    finished_at IS NULL with no staleness check. Mirrors
    MarketIntelligenceRepository.reap_stale_runs's already-proven fix
    for the identical failure mode on MarketScanRun."""
    session = session_factory()
    stale = IngestionRunLog(
        job_name="symbols",
        started_at=datetime.now(timezone.utc) - timedelta(hours=100),
        status=IngestionJobStatus.RUNNING,
    )
    session.add(stale)
    session.commit()
    stale_id = stale.id

    reaped = reap_stale_ingestion_runs(session, max_age_hours=6.0)
    assert [r.job_name for r in reaped] == ["symbols"]
    session.close()

    session = session_factory()
    row = session.query(IngestionRunLog).filter_by(id=stale_id).one()
    assert row.status == IngestionJobStatus.FAILED
    assert row.finished_at is not None
    assert "Reaped" in row.error_summary
    session.close()


def test_reap_stale_ingestion_runs_leaves_a_recent_running_row_alone(session_factory):
    session = session_factory()
    recent = IngestionRunLog(
        job_name="historical_ohlcv", started_at=datetime.now(timezone.utc), status=IngestionJobStatus.RUNNING
    )
    session.add(recent)
    session.commit()
    recent_id = recent.id
    session.close()

    session = session_factory()
    reaped = reap_stale_ingestion_runs(session, max_age_hours=6.0)
    session.close()

    assert reaped == []

    session = session_factory()
    row = session.query(IngestionRunLog).filter_by(id=recent_id).one()
    assert row.status == IngestionJobStatus.RUNNING
    assert row.finished_at is None
    session.close()


def test_reap_stale_ingestion_runs_leaves_already_finished_rows_alone(session_factory):
    session = session_factory()
    finished = IngestionRunLog(
        job_name="dividends",
        started_at=datetime.now(timezone.utc) - timedelta(hours=100),
        finished_at=datetime.now(timezone.utc) - timedelta(hours=99),
        status=IngestionJobStatus.SUCCESS,
    )
    session.add(finished)
    session.commit()
    session.close()

    session = session_factory()
    reaped = reap_stale_ingestion_runs(session, max_age_hours=6.0)
    session.close()

    assert reaped == []


# --- _find_quota_exceeded_cause -------------------------------------------


def test_find_quota_exceeded_cause_finds_a_direct_quota_error():
    exc = SahmkQuotaReservedForCriticalError("background dip into critical reserve")
    assert _find_quota_exceeded_cause(exc) is exc


def test_find_quota_exceeded_cause_walks_through_a_wrapped_strict_mode_error():
    """provider_factory/fundamental_provider_factory re-raise the rate
    limiter's own exception as StrictRealDataUnavailableError via a bare
    `raise NewError(...)` inside `except ... as exc:` -- Python sets
    __context__ automatically even with no explicit `raise ... from exc`.
    This must see through that wrapping."""
    try:
        try:
            raise SahmkUpstreamQuotaExhaustedError(
                "upstream 429", reset_at_utc=datetime.now(timezone.utc) + timedelta(hours=2)
            )
        except SahmkUpstreamQuotaExhaustedError:
            raise StrictRealDataUnavailableError("real data unavailable")
    except StrictRealDataUnavailableError as wrapped:
        found = _find_quota_exceeded_cause(wrapped)

    assert isinstance(found, SahmkUpstreamQuotaExhaustedError)


def test_find_quota_exceeded_cause_returns_none_for_an_unrelated_error():
    assert _find_quota_exceeded_cause(RuntimeError("some other failure")) is None


def test_find_quota_exceeded_cause_bounded_depth_does_not_infinite_loop():
    exc = RuntimeError("self-referential")
    exc.__context__ = exc  # pathological, must not hang
    assert _find_quota_exceeded_cause(exc) is None


# --- _compute_quota_retry_at -----------------------------------------------


def test_compute_quota_retry_at_uses_upstream_evidence_when_available():
    reset_at = datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc)
    quota_exc = SahmkUpstreamQuotaExhaustedError("upstream 429", reset_at_utc=reset_at)

    retry_at = _compute_quota_retry_at(quota_exc)

    assert retry_at == reset_at + _QUOTA_RETRY_SAFETY_BUFFER


def test_compute_quota_retry_at_falls_back_to_rate_limiters_own_reset_estimate(monkeypatch):
    fallback_reset = datetime(2026, 8, 13, 0, 0, 0, tzinfo=timezone.utc)

    class _FakeLimiter:
        def get_status(self):
            return {"resets_at_utc": fallback_reset.isoformat()}

    monkeypatch.setattr(
        "src.market_data.ingestion.scheduler.get_default_rate_limiter", lambda: _FakeLimiter()
    )
    quota_exc = SahmkQuotaReservedForCriticalError("background dip into critical reserve")

    retry_at = _compute_quota_retry_at(quota_exc)

    assert retry_at == fallback_reset + _QUOTA_RETRY_SAFETY_BUFFER


# --- run_ingestion_job: DEFERRED vs FAILED ---------------------------------


@pytest.mark.asyncio
async def test_run_ingestion_job_defers_on_quota_reserved_for_critical(session_factory):
    async def job_fn():
        raise SahmkQuotaReservedForCriticalError("background dip into critical reserve")

    run_log = await run_ingestion_job("test_job", job_fn, session_factory, max_attempts=3)

    assert run_log.status == IngestionJobStatus.DEFERRED
    assert run_log.next_retry_at is not None
    assert run_log.retry_count == 0  # no wasted backoff retries against a quota wall
    assert "Deferred" in run_log.error_summary


@pytest.mark.asyncio
async def test_run_ingestion_job_defers_on_quota_wrapped_in_strict_mode_error(session_factory):
    """The real production shape: provider_factory wraps the rate
    limiter's exception in StrictRealDataUnavailableError before it
    reaches the ingestion job function."""

    async def job_fn():
        try:
            raise SahmkUpstreamQuotaExhaustedError(
                "upstream 429", reset_at_utc=datetime.now(timezone.utc) + timedelta(hours=3)
            )
        except SahmkUpstreamQuotaExhaustedError:
            raise StrictRealDataUnavailableError("real data unavailable")

    run_log = await run_ingestion_job("test_job", job_fn, session_factory, max_attempts=3)

    assert run_log.status == IngestionJobStatus.DEFERRED
    assert run_log.next_retry_at is not None


@pytest.mark.asyncio
async def test_run_ingestion_job_still_fails_genuine_non_quota_errors(session_factory):
    """A quota deferral must never mask a real defect -- unrelated
    exceptions keep exhausting the full retry budget and are recorded
    FAILED exactly as before this change."""
    attempts = []

    async def job_fn():
        attempts.append(1)
        raise RuntimeError("genuine ingestion bug")

    run_log = await run_ingestion_job(
        "test_job", job_fn, session_factory, max_attempts=3, retry_base_delay_seconds=0.01
    )

    assert len(attempts) == 3
    assert run_log.status == IngestionJobStatus.FAILED
    assert run_log.next_retry_at is None


# --- IngestionScheduler: DEFERRED-aware rescheduling -----------------------


@pytest.mark.asyncio
async def test_loop_reschedules_a_deferred_job_at_next_retry_at_not_the_normal_interval(
    session_factory, monkeypatch
):
    """A quota-deferred job must wake up when the quota governor says
    background capacity returns, not on its own (possibly much longer)
    recurring interval -- otherwise a daily/weekly job deferred once
    could stay stale for a full extra cycle even after the quota reset."""
    sleep_calls = []

    async def _recording_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()  # stop the loop after one iteration

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    async def always_deferred():
        raise SahmkQuotaReservedForCriticalError("background dip into critical reserve")

    scheduler = IngestionScheduler(session_factory=session_factory)
    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop("test_job", lambda: 999999, always_deferred)

    assert len(sleep_calls) == 1
    # Sleeping for the huge normal interval (999999s) would be wrong here --
    # the deferral's own next_retry_at (a few minutes, given the fallback
    # reset is "tomorrow UTC midnight" plus the 5-minute safety buffer)
    # must win instead.
    assert sleep_calls[0] < 999999


@pytest.mark.asyncio
async def test_loop_uses_the_normal_interval_after_a_successful_run(session_factory, monkeypatch):
    sleep_calls = []

    async def _recording_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    async def succeeds():
        return IngestionResult(symbols_requested=1, symbols_succeeded=1)

    scheduler = IngestionScheduler(session_factory=session_factory)
    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop("test_job", lambda: 123.0, succeeds)

    assert sleep_calls == [123.0]


# --- IngestionScheduler._compute_initial_delay: restart resumption --------


def test_compute_initial_delay_is_zero_with_no_prior_run(session_factory):
    scheduler = IngestionScheduler(session_factory=session_factory)
    assert scheduler._compute_initial_delay("historical_ohlcv") == 0.0


def test_compute_initial_delay_is_zero_after_a_successful_prior_run(session_factory):
    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="historical_ohlcv",
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            finished_at=datetime.now(timezone.utc),
            status=IngestionJobStatus.SUCCESS,
        )
    )
    session.commit()
    session.close()

    scheduler = IngestionScheduler(session_factory=session_factory)
    assert scheduler._compute_initial_delay("historical_ohlcv") == 0.0


def test_compute_initial_delay_resumes_a_still_pending_deferral(session_factory):
    """The persisted-retry-state guarantee: a scheduler restart must not
    hammer the quota wall again -- it must honor the deferred job's
    already-recorded next_retry_at."""
    future_retry = datetime.now(timezone.utc) + timedelta(hours=2)
    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="historical_ohlcv",
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            finished_at=datetime.now(timezone.utc),
            status=IngestionJobStatus.DEFERRED,
            next_retry_at=future_retry,
        )
    )
    session.commit()
    session.close()

    scheduler = IngestionScheduler(session_factory=session_factory)
    delay = scheduler._compute_initial_delay("historical_ohlcv")

    assert 0 < delay <= 2 * 3600 + 1


def test_compute_initial_delay_is_zero_once_a_deferrals_retry_time_has_passed(session_factory):
    past_retry = datetime.now(timezone.utc) - timedelta(minutes=5)
    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="historical_ohlcv",
            started_at=datetime.now(timezone.utc) - timedelta(hours=5),
            finished_at=datetime.now(timezone.utc) - timedelta(hours=4),
            status=IngestionJobStatus.DEFERRED,
            next_retry_at=past_retry,
        )
    )
    session.commit()
    session.close()

    scheduler = IngestionScheduler(session_factory=session_factory)
    assert scheduler._compute_initial_delay("historical_ohlcv") == 0.0


@pytest.mark.asyncio
async def test_start_passes_the_resumed_initial_delay_into_each_loop(session_factory, monkeypatch):
    """Wiring proof: start() must actually thread _compute_initial_delay's
    result into _loop, not just compute it and drop it."""
    future_retry = datetime.now(timezone.utc) + timedelta(hours=1)
    session = session_factory()
    session.add(
        IngestionRunLog(
            job_name="symbols",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            finished_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status=IngestionJobStatus.DEFERRED,
            next_retry_at=future_retry,
        )
    )
    session.commit()
    session.close()

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

    seen_delays = {}
    real_loop = IngestionScheduler._loop

    async def _recording_loop(self, job_name, interval_fn, job_fn, initial_delay_seconds=0.0):
        seen_delays[job_name] = initial_delay_seconds
        raise asyncio.CancelledError()

    monkeypatch.setattr(IngestionScheduler, "_loop", _recording_loop)

    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler.start()
    # The autouse _instant_sleep fixture makes asyncio.sleep a no-op
    # coroutine with no internal suspension point, so awaiting it
    # directly never actually yields control back to the event loop --
    # the four just-scheduled tasks would never get a chance to run
    # before stop() cancels them while still pending. The real sleep(0)
    # is a genuine checkpoint.
    await _REAL_ASYNCIO_SLEEP(0)
    await scheduler.stop()

    assert seen_delays["symbols"] > 0
    assert seen_delays["historical_ohlcv"] == 0.0
    monkeypatch.setattr(IngestionScheduler, "_loop", real_loop)
