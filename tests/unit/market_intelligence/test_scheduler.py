"""Unit tests for IntervalMarketIntelligenceScheduler -- verifies the
start/stop lifecycle and that one loop iteration creates a
MarketScanRun and hands off to run_market_scan_job, without ever
running a real scan (run_market_scan_job is monkeypatched to a stub).

2026-08-13 SAHMK quota-exhaustion incident fix coverage: leader-lock
gating (only the leader actually scans), the quota circuit breaker
(`_quota_allows_a_new_cycle`), and the overlap guard
(`has_in_flight_run`) are all exercised here with fully fake
collaborators -- no real Redis, no real SAHMK rate limiter state, so
this file stays isolated from every other test module's mutations of
those process-wide singletons (the exact class of bug that made
`_no_real_shared_redis_by_default` necessary in
tests/unit/market_data/sahmk/test_rate_limiter.py).
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.market_intelligence.scheduler as scheduler_module
from src.core.db.database import Base
from src.domain.models import MarketScanRun, MarketScanStatus, Stock
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scheduler import IMarketIntelligenceScheduler, IntervalMarketIntelligenceScheduler
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock
from src.market_intelligence.types import ScheduleInterval


@pytest.fixture(autouse=True)
def _no_real_shared_redis_for_leader_lock_and_rate_limiter(monkeypatch):
    """Mirrors test_rate_limiter.py's own `_no_real_shared_redis_by_
    default` fixture, applied to BOTH process-wide singletons this
    module's tests can reach: `SchedulerLeaderLock()`'s default
    constructor and `SahmkRateLimiter(redis_client=None, ...)` (`None`
    there means "use the shared client," not "no Redis" -- see that
    class's own docstring) would otherwise both reach for real,
    process-wide shared Redis clients, making leadership and quota-
    status results depend on whatever the sandbox's Redis happens to
    hold -- flaky here, and a real risk of cross-test pollution through
    the same singletons other test modules also touch."""
    import src.market_data.sahmk.rate_limiter as rate_limiter_module
    import src.market_intelligence.scheduler_leader_lock as leader_lock_module

    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)
    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)
    yield


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    session.add(Stock(symbol="2222", name_en="Stock 2222", sector="Energy"))
    session.commit()
    session.close()
    yield session_factory
    Base.metadata.drop_all(bind=engine)


class _FakeProvider:
    pass


async def _fake_market_provider_getter():
    return _FakeProvider()


class _AlwaysLeaderLock:
    """Fake `SchedulerLeaderLock` double that always reports leadership
    without touching Redis at all -- for tests that need `_loop()` to
    actually invoke `_run_one_cycle` each tick."""

    def try_acquire_or_renew(self, lease_seconds: float) -> bool:
        return True

    def release(self) -> None:
        pass


class _NeverLeaderLock:
    """Fake double for the opposite case: proves `_loop()` skips
    `_run_one_cycle` entirely when this worker never wins/holds the
    lease."""

    def try_acquire_or_renew(self, lease_seconds: float) -> bool:
        return False

    def release(self) -> None:
        pass


def _always_allows_rate_limiter() -> SahmkRateLimiter:
    """A real `SahmkRateLimiter`, isolated from Redis by this module's
    autouse fixture (so `redis_client=None` here means the in-process
    fallback only) and never fed any usage -- its `get_status()`
    reports plenty of remaining quota, so tests using this double are
    exercising scheduler behavior, not rate-limiter behavior."""
    return SahmkRateLimiter(max_per_minute=20, max_per_day=4500, reserved_for_critical=1000, redis_client=None)


class _QuotaExhaustedRateLimiter:
    """Fake collaborator satisfying only the `get_status()` surface
    `_quota_allows_a_new_cycle` reads, reporting the exact
    upstream-confirmed-exhausted shape production observed on
    2026-08-13."""

    def get_status(self):
        return {
            "upstream_confirmed_exhausted": True,
            "remaining_today_for_background": 0,
        }


class _LowBackgroundQuotaRateLimiter:
    """Fake reporting quota that is not upstream-exhausted, but has
    dropped below MARKET_SCAN_MIN_BACKGROUND_QUOTA_REMAINING (default
    10) -- the circuit breaker must trip before that threshold is
    reached, not only once SAHMK itself refuses requests."""

    def get_status(self):
        return {
            "upstream_confirmed_exhausted": False,
            "remaining_today_for_background": 3,
        }


def test_satisfies_the_scheduler_protocol():
    scheduler = IntervalMarketIntelligenceScheduler()
    assert isinstance(scheduler, IMarketIntelligenceScheduler)


def test_is_not_running_before_start():
    scheduler = IntervalMarketIntelligenceScheduler()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle(factory, monkeypatch):
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory, market_provider_getter=_fake_market_provider_getter,
        interval=ScheduleInterval.EVERY_MINUTE,
    )
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_start_reaps_a_stale_running_scan_before_scheduling(factory):
    """A process kill leaves a MarketScanRun stuck RUNNING forever,
    which would otherwise permanently block POST /market/scan's overlap
    guard after a crash -- start() must reap it, not just future
    scheduled runs relying on someone noticing manually."""
    session = factory()
    stale_run = MarketScanRun(
        status=MarketScanStatus.RUNNING,
        symbols_requested=1,
        created_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    session.add(stale_run)
    session.commit()
    stale_run_id = stale_run.id
    session.close()

    scheduler = IntervalMarketIntelligenceScheduler(session_factory=factory, market_provider_getter=_fake_market_provider_getter)
    scheduler.start()
    await scheduler.stop()

    session = factory()
    reaped = session.query(MarketScanRun).filter_by(id=stale_run_id).one()
    assert reaped.status == MarketScanStatus.FAILED
    session.close()


@pytest.mark.asyncio
async def test_starting_twice_is_a_no_op(factory):
    scheduler = IntervalMarketIntelligenceScheduler(session_factory=factory, market_provider_getter=_fake_market_provider_getter)
    scheduler.start()
    first_task = scheduler._task
    scheduler.start()
    assert scheduler._task is first_task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_run_one_cycle_creates_a_run_and_delegates_to_the_job_runner(factory, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "false")
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    repo = MarketIntelligenceRepository()
    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        repository=repo,
        rate_limiter=_always_allows_rate_limiter(),
    )

    await scheduler._run_one_cycle()

    assert len(calls) == 1
    run_id, symbols = calls[0]
    assert symbols == ["2222"]

    session = factory()
    run = repo.get_run(session, run_id)
    assert run is not None
    session.close()


@pytest.mark.asyncio
async def test_run_one_cycle_skips_when_upstream_quota_confirmed_exhausted(factory, monkeypatch):
    """The circuit breaker must stop the cycle before it touches the DB
    or SAHMK at all once upstream has confirmed the daily quota is
    gone -- zero new MarketScanRun rows, zero job-runner calls."""
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        rate_limiter=_QuotaExhaustedRateLimiter(),
    )

    await scheduler._run_one_cycle()

    assert calls == []
    session = factory()
    assert session.query(MarketScanRun).count() == 0
    session.close()


@pytest.mark.asyncio
async def test_run_one_cycle_skips_when_background_quota_reserve_is_low(factory, monkeypatch):
    """Below MARKET_SCAN_MIN_BACKGROUND_QUOTA_REMAINING, the scheduler
    must stop itself proactively rather than wait for a live acquire()
    failure mid-scan -- protecting the reserve is the whole point."""
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        rate_limiter=_LowBackgroundQuotaRateLimiter(),
    )

    await scheduler._run_one_cycle()

    assert calls == []


@pytest.mark.asyncio
async def test_run_one_cycle_skips_when_a_scan_is_already_in_flight(factory, monkeypatch):
    """The overlap guard (`has_in_flight_run`) must prevent the
    scheduler from starting a second concurrent cycle -- the exact gate
    POST /market/scan and the admin diagnostic-scan route already had,
    now shared via MarketIntelligenceRepository.has_in_flight_run."""
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    session = factory()
    session.add(MarketScanRun(status=MarketScanStatus.RUNNING, symbols_requested=1))
    session.commit()
    session.close()

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        rate_limiter=_always_allows_rate_limiter(),
    )

    await scheduler._run_one_cycle()

    assert calls == []


@pytest.mark.asyncio
async def test_run_one_cycle_runs_under_background_priority(factory, monkeypatch):
    """The 2026-08-13 incident's primary root cause: this call path
    must be tagged BACKGROUND so it is subject to
    `reserved_for_critical`'s reserve, unlike the unmarked (CRITICAL by
    default) priority it ran under before this fix."""
    from src.market_data.sahmk.request_priority import get_current_priority

    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "false")
    observed_priority = {}

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        observed_priority["value"] = get_current_priority()

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        rate_limiter=_always_allows_rate_limiter(),
    )

    await scheduler._run_one_cycle()

    from src.market_data.sahmk.request_priority import BACKGROUND

    assert observed_priority["value"] == BACKGROUND


@pytest.mark.asyncio
async def test_loop_only_runs_a_cycle_while_this_worker_is_leader(factory, monkeypatch):
    """Proves the fix for the 2026-08-13 4x multi-worker duplication:
    a worker that never wins the leader lease must never invoke
    `_run_one_cycle` from the loop at all."""
    monkeypatch.setattr(scheduler_module, "schedule_interval_seconds", lambda interval: 0.01)

    call_count = {"n": 0}

    async def _counting_run_one_cycle():
        call_count["n"] += 1

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        leader_lock=_NeverLeaderLock(),
    )
    scheduler._run_one_cycle = _counting_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] == 0


@pytest.mark.asyncio
async def test_loop_runs_cycles_while_this_worker_is_leader(factory, monkeypatch):
    monkeypatch.setattr(scheduler_module, "schedule_interval_seconds", lambda interval: 0.01)

    call_count = {"n": 0}

    async def _counting_run_one_cycle():
        call_count["n"] += 1

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        leader_lock=_AlwaysLeaderLock(),
    )
    scheduler._run_one_cycle = _counting_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


@pytest.mark.asyncio
async def test_loop_survives_an_exception_and_keeps_scheduling(factory, monkeypatch):
    """A failure creating the run row itself (not a scan failure --
    that's already caught inside run_market_scan_job) must not kill
    the scheduler's loop."""
    call_count = {"n": 0}

    async def _raising_run_one_cycle():
        call_count["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "schedule_interval_seconds", lambda interval: 0.01)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        leader_lock=_AlwaysLeaderLock(),
    )
    scheduler._run_one_cycle = _raising_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


def test_default_leader_lock_is_a_scheduler_leader_lock():
    scheduler = IntervalMarketIntelligenceScheduler()
    assert isinstance(scheduler._leader_lock, SchedulerLeaderLock)
