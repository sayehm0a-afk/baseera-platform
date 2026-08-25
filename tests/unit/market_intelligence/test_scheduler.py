"""Unit tests for IntervalMarketIntelligenceScheduler -- verifies the
start/stop lifecycle and that one loop iteration delegates to
run_radar_v2_cycle (Stage 1 local ranking -> Stage 2 bounded live
validation -> RadarOpportunity emission), without ever running a real
Stage 1 scan or a real SAHMK call (run_radar_v2_cycle and
run_market_scan_job are both monkeypatched/injected as fakes).
`_stage2_runner` -- the scheduler's own Stage 2 callable, the one part
of this module that actually creates a MarketScanRun and calls
run_market_scan_job -- is exercised directly in the tests that need
to observe that behavior, so this file doesn't need real OHLCV/
technical fixtures for Stage 1's ranking logic (already covered by
tests/unit/market_intelligence/test_stage1_local_scan.py and
tests/unit/market_intelligence/test_radar_v2.py).

2026-08-13 SAHMK quota-exhaustion incident fix coverage: leader-lock
gating (only the leader actually scans), the quota circuit breaker
(`_quota_allows_a_new_cycle`), and the overlap guard
(`has_in_flight_run`) are all exercised here with fully fake
collaborators -- no real Redis, no real SAHMK rate limiter state, so
this file stays isolated from every other test module's mutations of
those process-wide singletons (the exact class of bug that made
`_no_real_shared_redis_by_default` necessary in
tests/unit/market_data/sahmk/test_rate_limiter.py).

2026-08-18 real-market validation audit fix coverage: this scheduler
used to pick its own stale-first symbol batch and never wrote a
RadarOpportunity row, so a real user's Radar page was always empty
even while this scheduler ran continuously -- see scheduler.py's own
module docstring. The tests below verify the scheduler now delegates
to run_radar_v2_cycle (real by default, injectable here) with
_stage2_runner as the Stage 2 callable.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.market_intelligence.scheduler as scheduler_module
from src.core.db.database import Base
from src.domain.models import MarketScanRun, MarketScanStatus, Stock
from src.market_data.sahmk.operation_scope import get_current_operation
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scheduler import IMarketIntelligenceScheduler, IntervalMarketIntelligenceScheduler
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock
from src.market_intelligence.types import ScheduleInterval


@dataclass
class _FakeRadarV2Result:
    """Scheduler-side double of `radar_v2.RadarV2RunResult`, matching
    only the fields `_run_one_cycle` actually reads."""

    stage2_executed: bool
    stage1_candidate_count: int = 0
    stage1_universe_size: int = 0
    stage2_stop_reason: Optional[str] = None
    scan_run_id: Optional[int] = None
    opportunities_emitted: list = None
    opportunities_suppressed_as_duplicate: list = None

    def __post_init__(self):
        if self.opportunities_emitted is None:
            self.opportunities_emitted = []
        if self.opportunities_suppressed_as_duplicate is None:
            self.opportunities_suppressed_as_duplicate = []


def _fake_run_radar_v2_cycle_calling_stage2(symbols: List[str]):
    """Builds a fake `run_radar_v2_cycle` that skips real Stage 1
    entirely and calls the injected Stage 2 runner (the scheduler's
    real `_stage2_runner`) with a fixed candidate list -- proving
    `_run_one_cycle` wires the real Stage 2 callable through
    correctly, without needing real price-history fixtures for Stage
    1's own ranking logic."""

    async def _fake(session, stage2_runner):
        result = await stage2_runner(session, "scheduled_radar_v2", lambda: symbols)
        return _FakeRadarV2Result(
            stage2_executed=result.executed,
            stage1_candidate_count=len(symbols),
            stage1_universe_size=len(symbols),
            stage2_stop_reason=result.stop_reason,
            scan_run_id=result.run_id,
        )

    return _fake


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
            "remaining_today_for_background_after_live_scan_reserve": 3,
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
async def test_run_one_cycle_delegates_to_run_radar_v2_cycle_and_its_stage2_creates_a_run(factory, monkeypatch):
    """`_run_one_cycle` no longer selects symbols itself -- it hands
    off to `run_radar_v2_cycle`, which (via the scheduler's real
    `_stage2_runner`, exercised here through the fake Stage 1) still
    ends up creating a real MarketScanRun and calling
    `run_market_scan_job`, exactly as the pre-Radar-V2 wiring did."""
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
        run_radar_v2_cycle=_fake_run_radar_v2_cycle_calling_stage2(["2222"]),
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
async def test_run_one_cycle_uses_the_real_run_radar_v2_cycle_by_default(factory, monkeypatch):
    """Without an injected double, `_run_one_cycle` must go through the
    real `run_radar_v2_cycle` (real Stage 1) -- with the single-stock,
    no-price-history fixture this module's `factory` provides, Stage 1
    finds no candidates, so this proves the real wiring is reached and
    degrades to zero SAHMK calls rather than silently doing nothing."""
    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "false")
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        rate_limiter=_always_allows_rate_limiter(),
    )

    await scheduler._run_one_cycle()

    assert calls == []


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


class _LiveScanReserveProtectedRateLimiter:
    """P0 remediation (independent PR #99 audit, P2 finding #2): the
    legacy remaining_today_for_background field looks healthy, but the
    live-scan-aware field is low -- the circuit breaker must still
    trip, proving _quota_allows_a_new_cycle reads the correct field."""

    def get_status(self):
        return {
            "upstream_confirmed_exhausted": False,
            "remaining_today_for_background": 40,  # legacy field: looks healthy
            "remaining_today_for_background_after_live_scan_reserve": 3,  # true budget: low
        }


@pytest.mark.asyncio
async def test_run_one_cycle_stops_when_only_the_live_scan_reserve_is_protecting_the_budget(
    factory, monkeypatch
):
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
        rate_limiter=_LiveScanReserveProtectedRateLimiter(),
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
async def test_stage2_runner_runs_under_background_priority_and_radar_v2_operation(factory, monkeypatch):
    """The 2026-08-13 incident's primary root cause: this call path
    must be tagged BACKGROUND so it is subject to
    `reserved_for_critical`'s reserve, unlike the unmarked (CRITICAL by
    default) priority it ran under before that fix. Separately, the
    2026-08-18 Radar V2 wiring must tag its SAHMK usage `RADAR_V2` (not
    the old `MARKET_SCAN`) so it is attributable in
    `GET .../radar-v2/sahmk-consumption` -- both observed directly from
    `_stage2_runner`, the one piece of this module that still calls
    `run_market_scan_job`."""
    from src.market_data.sahmk.request_priority import BACKGROUND, get_current_priority

    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "false")
    observed = {}

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        observed["priority"] = get_current_priority()
        observed["operation"] = get_current_operation()

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory,
        market_provider_getter=_fake_market_provider_getter,
    )

    session = factory()
    result = await scheduler._stage2_runner(session, "scheduled_radar_v2", lambda: ["2222"])
    session.close()

    assert result.executed is True
    assert observed["priority"] == BACKGROUND
    assert observed["operation"] == "radar_v2"


@pytest.mark.asyncio
async def test_stage2_runner_reports_no_candidates_without_touching_the_db(factory):
    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory, market_provider_getter=_fake_market_provider_getter
    )
    session = factory()
    result = await scheduler._stage2_runner(session, "scheduled_radar_v2", lambda: [])
    session.close()

    assert result.executed is False
    assert result.stop_reason == "no_candidates"


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
