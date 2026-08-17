"""Regression tests for the 2026-08-17 IngestionScheduler leader-lock
fix -- root cause: `main.py`'s `@app.on_event("startup")` runs
independently in every one of Gunicorn's 4 worker processes
(Dockerfile: `--workers 4`), so `IngestionScheduler.start()` ran 4
times, each driving its own full, redundant set of the four ingestion
job loops against the identical symbol universe (confirmed production
evidence: ~2.8x-3.6x the expected per-symbol SAHMK call count for
OHLCV/fundamentals/dividends).

Covers the mandate's TEST1-TEST10 acceptance list. Mirrors
tests/unit/market_intelligence/test_scheduler_leader_lock.py's
in-memory `_FakeRedis`/`_BrokenRedis` pattern so every test here proves
real cross-instance leadership behavior without a live Redis server.
"""

import asyncio
import contextlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.market_intelligence.scheduler_leader_lock as leader_lock_module
from src.core.db.database import Base
from src.domain.models import IngestionJobStatus, IngestionRunLog
from src.market_data.ingestion._common import IngestionResult
from src.market_data.ingestion.scheduler import IngestionScheduler
from src.market_data.sahmk.rate_limiter import SahmkQuotaReservedForCriticalError
from src.market_intelligence.scheduler import IntervalMarketIntelligenceScheduler
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock

_TEST_LEASE_KEY = "basirah:ingestion_scheduler:leader:test"

# Captured before the autouse _instant_sleep fixture patches asyncio.sleep
# to a no-op -- a coroutine cancelled before its very first `__step` never
# executes any of its body (asyncio throws CancelledError in instead of
# resuming it), so tests proving a freshly `start()`-ed loop task actually
# ran at least once need one genuine `await` to give the event loop a
# chance to run it before `stop()` cancels it.
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


@pytest.fixture(autouse=True)
def _no_real_shared_redis(monkeypatch):
    """See test_scheduler.py's identical fixture -- every test in this
    file must be isolated from any real, process-wide shared Redis
    client; tests that need real cross-instance sharing pass their own
    `_FakeRedis` via `SchedulerLeaderLock(redis_client=...)`, which is
    unaffected by this patch."""
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)


class _FakeRedis:
    """In-memory stand-in for redis.Redis -- covers exactly the
    operations SchedulerLeaderLock uses. Identical to the fake used in
    test_scheduler_leader_lock.py, duplicated here (not imported) to
    keep this test file self-contained, matching that file's own
    stated convention of not sharing test doubles across modules."""

    def __init__(self):
        self._kv: dict = {}

    def get(self, key):
        return self._kv.get(key)

    def set(self, key, value, nx=False, px=None):
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def pexpire(self, key, ttl_ms):
        return key in self._kv

    def delete(self, key):
        self._kv.pop(key, None)

    def expire_now(self, key):
        """Simulates a lease TTL expiring (e.g. the previous leader's
        process crashed without releasing it)."""
        self._kv.pop(key, None)


class _BrokenRedis:
    """Every operation raises -- a Redis connection reachable at
    client-construction time but failing on each real call."""

    def get(self, key):
        raise ConnectionError("simulated Redis outage")

    def set(self, key, value, nx=False, px=None):
        raise ConnectionError("simulated Redis outage")

    def pexpire(self, key, ttl_ms):
        raise ConnectionError("simulated Redis outage")

    def delete(self, key):
        raise ConnectionError("simulated Redis outage")


def _scheduler_on(session_factory, redis, lease_key=_TEST_LEASE_KEY):
    return IngestionScheduler(
        session_factory=session_factory,
        leader_lock=SchedulerLeaderLock(redis_client=redis, lease_key=lease_key),
    )


async def _crash_without_releasing(scheduler: IngestionScheduler) -> None:
    """Simulates a killed/restarted process: cancels this scheduler's
    tasks directly WITHOUT calling stop() (which would release the
    lease cleanly) -- the whole point of a lease is that a real crash
    never gets a chance to release anything.

    Cancels every task (leadership heartbeat AND all job loops) before
    awaiting any of them -- same ordering requirement as
    IngestionScheduler.stop() itself: awaiting one task hands control
    back to the event loop, which would otherwise get a chance to run
    any not-yet-cancelled task's real body (this file's autouse
    instant-sleep fixture makes `_loop`/`_leadership_heartbeat_loop`'s
    own `await asyncio.sleep(...)` never actually suspend, so a task
    that starts running never stops)."""
    if scheduler._leadership_task is not None:
        scheduler._leadership_task.cancel()
    for task in scheduler._tasks:
        task.cancel()
    if scheduler._leadership_task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler._leadership_task
    for task in scheduler._tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _stop_all(schedulers) -> None:
    """Stops several started-but-never-ticked schedulers that share the
    same event loop. Awaiting one scheduler's own stop() in isolation
    is safe on its own (IngestionScheduler.stop() cancels all of ITS
    tasks before awaiting any of them) -- but stopping schedulers one
    at a time in a loop is not: the first scheduler's `await` inside
    its own stop() hands control back to the event loop, which would
    then get a chance to run a *different*, not-yet-cancelled
    scheduler's tasks for the first time (their real bodies, under this
    file's non-yielding instant-sleep fixture, would then spin
    forever). Cancelling every task on every scheduler up front, before
    any of them are awaited, avoids that."""
    for scheduler in schedulers:
        if scheduler._leadership_task is not None:
            scheduler._leadership_task.cancel()
        for task in scheduler._tasks:
            task.cancel()
    for scheduler in schedulers:
        await scheduler.stop()


# --- TEST1: single leader ---------------------------------------------


@pytest.mark.asyncio
async def test_exactly_one_of_four_scheduler_instances_becomes_leader(session_factory):
    """TEST1 (mandate): 4 IngestionScheduler instances sharing the same
    Redis-backed lease -- simulating 4 Gunicorn worker processes each
    running their own in-process scheduler against the same Redis --
    exactly one must hold leadership."""
    redis = _FakeRedis()
    schedulers = [_scheduler_on(session_factory, redis) for _ in range(4)]

    for scheduler in schedulers:
        scheduler.start()
    try:
        leader_flags = [scheduler.is_leader for scheduler in schedulers]
        assert sum(leader_flags) == 1
    finally:
        await _stop_all(schedulers)


# --- TEST2: followers do nothing ---------------------------------------


@pytest.mark.asyncio
async def test_non_leader_worker_never_executes_ingestion_work(session_factory, monkeypatch):
    """TEST2 (mandate): a follower (not holding leadership) must never
    call the SAHMK-consuming ingestion job function -- zero cost, zero
    IngestionRunLog row written, only the skip counter moves."""
    sleep_calls = []

    async def _recording_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    calls = []

    async def job_fn():
        calls.append(1)
        return IngestionResult(symbols_requested=1, symbols_succeeded=1)

    scheduler = IngestionScheduler(session_factory=session_factory)
    assert scheduler.is_leader is False  # never started -- default not-leader

    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop("historical_ohlcv", lambda: 100.0, job_fn)

    assert calls == []
    assert scheduler.skipped_due_to_not_leader_count == 1

    session = session_factory()
    assert session.query(IngestionRunLog).count() == 0
    session.close()


# --- TEST3: leader failover ---------------------------------------------


@pytest.mark.asyncio
async def test_leader_failover_after_the_previous_leaders_lease_expires(session_factory):
    """TEST3 (mandate): the crashed leader's lease expiring (it never
    got to release it) must let another worker safely become leader --
    no permanent outage."""
    redis = _FakeRedis()
    crashed_leader = _scheduler_on(session_factory, redis)
    crashed_leader.start()
    assert crashed_leader.is_leader is True
    await _crash_without_releasing(crashed_leader)

    redis.expire_now(_TEST_LEASE_KEY)  # the crashed leader's TTL running out

    new_leader = _scheduler_on(session_factory, redis)
    new_leader.start()
    try:
        assert new_leader.is_leader is True
    finally:
        await new_leader.stop()


# --- TEST4: no split brain ----------------------------------------------


@pytest.mark.asyncio
async def test_no_split_brain_even_across_a_contested_reacquisition(session_factory):
    """TEST4 (mandate): never two active leaders executing the same
    recurring workload -- including immediately after a failover, when
    every surviving worker tries to claim the now-vacant lease at once."""
    redis = _FakeRedis()
    original = _scheduler_on(session_factory, redis)
    original.start()
    assert original.is_leader is True
    await _crash_without_releasing(original)
    redis.expire_now(_TEST_LEASE_KEY)

    contenders = [_scheduler_on(session_factory, redis) for _ in range(3)]
    for contender in contenders:
        contender.start()
    try:
        assert sum(contender.is_leader for contender in contenders) == 1
    finally:
        await _stop_all(contenders)


# --- TEST5: Redis failure behavior is quota-safe -------------------------


@pytest.mark.asyncio
async def test_redis_failure_fails_closed_and_stays_quota_safe(session_factory, monkeypatch):
    """TEST5 (mandate): if Redis is unreachable, no worker may assume
    leadership -- silently reverting to "every worker runs the job"
    would reopen the exact incident this fix closes. A fleet where
    every worker fails closed does zero ingestion work rather than N.
    """
    scheduler = _scheduler_on(session_factory, _BrokenRedis())
    scheduler.start()
    try:
        assert scheduler.is_leader is False
    finally:
        await scheduler.stop()

    sleep_calls = []

    async def _recording_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    calls = []

    async def job_fn():
        calls.append(1)
        return IngestionResult(symbols_requested=1, symbols_succeeded=1)

    scheduler2 = _scheduler_on(session_factory, _BrokenRedis())
    with pytest.raises(asyncio.CancelledError):
        await scheduler2._loop("historical_ohlcv", lambda: 100.0, job_fn)

    assert calls == []  # no SAHMK-consuming work happened despite the Redis outage


# --- TEST6: MarketIntelligenceScheduler remains unaffected ---------------


def test_market_intelligence_scheduler_keeps_its_own_independent_lease_key(session_factory):
    """TEST6 (mandate): the pre-existing, already-proven
    MarketIntelligenceScheduler leader lock must be untouched by this
    fix -- each scheduler tracks leadership under its own key, so a
    worker could legitimately lead one but not the other."""
    mi_scheduler = IntervalMarketIntelligenceScheduler()
    ingestion_scheduler = IngestionScheduler(session_factory=session_factory)

    assert mi_scheduler._leader_lock._lease_key == "basirah:scheduler:market_intelligence:leader"
    assert ingestion_scheduler._leader_lock._lease_key == "basirah:ingestion_scheduler:leader"
    assert mi_scheduler._leader_lock._lease_key != ingestion_scheduler._leader_lock._lease_key


# --- TEST7 + TEST8: deferred ingestion / critical-reserve protection -----
# still work correctly for a genuinely-elected leader ---------------------


@pytest.mark.asyncio
async def test_leader_elected_via_real_lock_still_defers_on_critical_reserve_protection(
    session_factory, monkeypatch
):
    """TEST7 + TEST8 (mandate): leadership gating must not interfere
    with the pre-existing SAHMK background-quota protection. A worker
    that genuinely won leadership through the real lock (not a fake
    double) must still (a) actually attempt the job -- proving it
    never draws from the protected critical reserve, since the
    reservation error is what correctly refuses it -- and (b)
    reschedule at the quota governor's own next_retry_at, not the
    job's normal (possibly much longer) interval."""
    redis = _FakeRedis()
    lock = SchedulerLeaderLock(redis_client=redis, lease_key=_TEST_LEASE_KEY)
    assert lock.try_acquire_or_renew(lease_seconds=180) is True

    scheduler = IngestionScheduler(session_factory=session_factory, leader_lock=lock)
    scheduler._is_leader = True  # what start()'s synchronous acquisition would have set

    sleep_calls = []

    async def _recording_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    attempts = []

    async def always_reserved_for_critical():
        attempts.append(1)
        raise SahmkQuotaReservedForCriticalError("background dip into critical reserve")

    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop("historical_ohlcv", lambda: 999999, always_reserved_for_critical)

    assert attempts == [1]  # the leader genuinely attempted the job (not silently skipped)
    assert len(sleep_calls) == 1
    assert sleep_calls[0] < 999999  # rescheduled at next_retry_at, not the huge normal interval

    session = session_factory()
    run = session.query(IngestionRunLog).filter_by(job_name="historical_ohlcv").one()
    assert run.status == IngestionJobStatus.DEFERRED
    session.close()


# --- TEST9: job cadence is untouched by this fix --------------------------
# Covered by the pre-existing, unmodified tests in test_config.py
# (get_ohlcv_sync_next_delay_seconds) and test_trading_calendar.py
# (seconds_until_next_ohlcv_sync) -- this fix only changes *whether*
# _loop's existing body runs on a given tick, never *when* (job_specs
# and every interval_fn in scheduler.py are byte-identical to before).


@pytest.mark.asyncio
async def test_ohlcv_job_spec_still_uses_the_calendar_aware_interval_function(
    session_factory, monkeypatch
):
    """Structural guard: proves start()'s job_specs wiring for
    historical_ohlcv still passes get_ohlcv_sync_next_delay_seconds as
    its interval_fn -- unchanged by the leadership fix, which only
    touches whether a tick's work runs, never which interval function a
    job uses.

    Mirrors test_scheduler.py's own
    test_start_passes_the_resumed_initial_delay_into_each_loop pattern:
    replaces _loop (AND _leadership_heartbeat_loop -- also a real
    `while True: await asyncio.sleep(...)` body started by start())
    with stubs that raise immediately, rather than letting either real
    while-loop (whose own `await asyncio.sleep(...)` resolves to this
    file's non-yielding instant-sleep fixture) run at all -- either one
    would otherwise never hand control back to the event loop and hang
    the test."""
    import src.market_data.ingestion.config as ingestion_config

    seen_interval_fns = {}

    async def _recording_loop(self, job_name, interval_fn, job_fn, initial_delay_seconds=0.0):
        seen_interval_fns[job_name] = interval_fn
        raise asyncio.CancelledError()

    async def _stub_heartbeat_loop(self):
        raise asyncio.CancelledError()

    monkeypatch.setattr(IngestionScheduler, "_loop", _recording_loop)
    monkeypatch.setattr(IngestionScheduler, "_leadership_heartbeat_loop", _stub_heartbeat_loop)

    scheduler = IngestionScheduler(session_factory=session_factory)
    scheduler.start()
    await _REAL_ASYNCIO_SLEEP(0)  # let each job task run its first tick before stop() cancels it
    await scheduler.stop()

    assert seen_interval_fns["historical_ohlcv"] is ingestion_config.get_ohlcv_sync_next_delay_seconds


# --- TEST10: existing ingestion tests remain green ------------------------
# Enforced by running the full tests/unit/market_data/ingestion/
# test_scheduler.py suite (3 tests there were updated to explicitly set
# leadership, since they call _loop()/spawn a loop task directly and
# bypass start() -- see that file's own comments) alongside this file,
# plus the full backend suite, as part of verification before merge.
