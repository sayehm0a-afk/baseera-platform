"""Regression tests for the 2026-08-19 DecisionV2OutcomeScheduler
leader-lock fix -- root cause: `main.py`'s `@app.on_event("startup")`
runs independently in every one of Gunicorn's 4 worker processes
(Dockerfile: `--workers 4`), so `DecisionV2OutcomeScheduler.start()` ran
4 times, each driving its own full, redundant evaluation cycle at the
identical wall-clock offset every interval -- confirmed production
evidence (2026-08-18 22:17-22:18 verification): 4 near-simultaneous
"DecisionV2Outcome evaluation cycle:" log lines every 3600s instead of
one. Mirrors tests/unit/market_data/ingestion/
test_scheduler_leadership.py's in-memory `_FakeRedis`/`_BrokenRedis`
pattern so every test here proves real cross-instance leadership
behavior without a live Redis server.
"""

import asyncio
import contextlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.market_intelligence.scheduler_leader_lock as leader_lock_module
from src.ai_evolution.scheduler import DecisionV2OutcomeScheduler
from src.core.db.database import Base
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, Stock
from src.market_intelligence.scheduler import IntervalMarketIntelligenceScheduler
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock

_TEST_LEASE_KEY = "basirah:decision_v2_outcome_scheduler:leader:test"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
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
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)


class _FakeRedis:
    """In-memory stand-in for redis.Redis -- covers exactly the
    operations SchedulerLeaderLock uses. Identical to the fake used in
    test_scheduler_leader_lock.py / test_scheduler_leadership.py,
    duplicated here (not imported) to keep this test file
    self-contained, matching that file's own stated convention."""

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


def _scheduler_on(session_factory, redis, lease_key=_TEST_LEASE_KEY, interval_seconds=3600):
    return DecisionV2OutcomeScheduler(
        session_factory=session_factory,
        interval_seconds=interval_seconds,
        leader_lock=SchedulerLeaderLock(redis_client=redis, lease_key=lease_key),
    )


async def _crash_without_releasing(scheduler: DecisionV2OutcomeScheduler) -> None:
    """Simulates a killed/restarted process: cancels this scheduler's
    tasks directly WITHOUT calling stop() (which would release the
    lease cleanly) -- the whole point of a lease is that a real crash
    never gets a chance to release anything."""
    if scheduler._leadership_task is not None:
        scheduler._leadership_task.cancel()
    if scheduler._task is not None:
        scheduler._task.cancel()
    if scheduler._leadership_task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler._leadership_task
    if scheduler._task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler._task


async def _stop_all(schedulers) -> None:
    """Stops several started-but-never-ticked schedulers sharing the
    same event loop -- see test_scheduler_leadership.py's identical
    helper/comment for why every task must be cancelled up front,
    before any of them are awaited."""
    for scheduler in schedulers:
        if scheduler._leadership_task is not None:
            scheduler._leadership_task.cancel()
        if scheduler._task is not None:
            scheduler._task.cancel()
    for scheduler in schedulers:
        await scheduler.stop()


def _stock(session, symbol="2222"):
    row = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(row)
    session.commit()
    return row


def _pending_snapshot_and_outcome(session, stock):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision="BUY_CANDIDATE",
        decision_label_ar="شراء",
        confidence_score=70.0,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=100.0,
        target_1=110.0,
        target_2=120.0,
        target_3=130.0,
        stop_loss=90.0,
        market_status="OPEN",
        decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
    )
    session.add(snapshot)
    session.flush()
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        symbol=stock.symbol,
        due_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        status=DecisionV2OutcomeStatus.PENDING,
        entry_price=100.0,
    )
    session.add(outcome)
    session.commit()
    return snapshot, outcome


# --- TEST1: single leader among concurrent workers ------------------------


@pytest.mark.asyncio
async def test_exactly_one_of_four_scheduler_instances_becomes_leader(session_factory):
    """4 DecisionV2OutcomeScheduler instances sharing the same
    Redis-backed lease -- simulating 4 Gunicorn worker processes each
    running their own in-process scheduler against the same Redis --
    exactly one must hold leadership. Directly proves concurrent workers
    cannot both run the same evaluation cycle simultaneously."""
    redis = _FakeRedis()
    schedulers = [_scheduler_on(session_factory, redis) for _ in range(4)]

    for scheduler in schedulers:
        scheduler.start()
    try:
        leader_flags = [scheduler.is_leader for scheduler in schedulers]
        assert sum(leader_flags) == 1
    finally:
        await _stop_all(schedulers)


# --- TEST2: followers skip entirely -----------------------------------


@pytest.mark.asyncio
async def test_non_leader_worker_never_runs_an_evaluation_cycle(session_factory, monkeypatch):
    """A follower (not holding leadership) must never call
    evaluate_pending_outcomes -- zero DB work, only the skip counter
    moves."""
    scheduler = DecisionV2OutcomeScheduler(session_factory=session_factory, interval_seconds=999999)
    assert scheduler.is_leader is False  # never started -- default not-leader

    calls = []

    async def _counting_run_one_cycle():
        calls.append(1)

    scheduler._run_one_cycle = _counting_run_one_cycle

    async def _recording_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop()

    assert calls == []
    assert scheduler.skipped_due_to_not_leader_count == 1


# --- TEST3: leader failover after a crash -------------------------------


@pytest.mark.asyncio
async def test_leader_failover_after_the_previous_leaders_lease_expires(session_factory):
    """The crashed leader's lease expiring (it never got to release it)
    must let another worker safely become leader -- no permanent
    outage."""
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


# --- TEST4: no split brain across a contested reacquisition --------------


@pytest.mark.asyncio
async def test_no_split_brain_even_across_a_contested_reacquisition(session_factory):
    """Never two active leaders executing the same recurring evaluation
    cycle -- including immediately after a failover, when every
    surviving worker tries to claim the now-vacant lease at once."""
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


# --- TEST5: Redis failure fails closed, not open --------------------------


@pytest.mark.asyncio
async def test_redis_failure_fails_closed(session_factory, monkeypatch):
    """If Redis is unreachable, no worker may assume leadership --
    silently reverting to "every worker evaluates" would reopen the
    exact multi-worker duplication this fix closes."""
    scheduler = _scheduler_on(session_factory, _BrokenRedis())
    scheduler.start()
    try:
        assert scheduler.is_leader is False
    finally:
        await scheduler.stop()

    calls = []

    async def _counting_run_one_cycle():
        calls.append(1)

    async def _recording_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    scheduler2 = _scheduler_on(session_factory, _BrokenRedis())
    scheduler2._run_one_cycle = _counting_run_one_cycle
    with pytest.raises(asyncio.CancelledError):
        await scheduler2._loop()

    assert calls == []  # no evaluation work happened despite the Redis outage


# --- TEST6: independent lease key from the other two schedulers ----------


def test_lease_key_is_independent_of_the_other_two_schedulers(session_factory):
    """Each scheduler tracks leadership under its own key -- a worker
    could legitimately lead one but not another."""
    decision_v2_scheduler = DecisionV2OutcomeScheduler(session_factory=session_factory)
    mi_scheduler = IntervalMarketIntelligenceScheduler()

    assert decision_v2_scheduler._leader_lock._lease_key == "basirah:decision_v2_outcome_scheduler:leader"
    assert mi_scheduler._leader_lock._lease_key == "basirah:scheduler:market_intelligence:leader"
    assert decision_v2_scheduler._leader_lock._lease_key != mi_scheduler._leader_lock._lease_key


# --- TEST7: no duplicate DecisionV2Outcome rows + DecisionV2Snapshot -----
# immutability, proven against the real (unmocked) evaluation function ----


@pytest.mark.asyncio
async def test_running_the_real_evaluation_cycle_repeatedly_creates_no_duplicates_and_never_mutates_the_snapshot(
    session_factory,
):
    """Directly proves the two invariants the mandate calls out by name:
    no duplicate DecisionV2Outcome rows, and DecisionV2Snapshot stays
    immutable -- against the real (not mocked) evaluate_pending_outcomes
    path, called twice in a row (the strongest local proxy for "two
    workers both thought they were leader": even if that ever happened,
    the underlying evaluation function's own idempotency and the DB's
    unique constraint hold)."""
    session = session_factory()
    stock = _stock(session)
    snapshot, _outcome = _pending_snapshot_and_outcome(session, stock)
    snapshot_id = snapshot.id
    original_values = {
        "decision": snapshot.decision,
        "current_price": float(snapshot.current_price),
        "target_1": float(snapshot.target_1),
        "target_2": float(snapshot.target_2),
        "target_3": float(snapshot.target_3),
        "stop_loss": float(snapshot.stop_loss),
        "decision_timestamp": snapshot.decision_timestamp,
    }
    session.close()

    scheduler = DecisionV2OutcomeScheduler(session_factory=session_factory, interval_seconds=3600)

    await scheduler._run_one_cycle()
    await scheduler._run_one_cycle()  # a second real cycle -- must not duplicate or mutate anything

    verify = session_factory()
    outcomes = verify.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot_id).all()
    assert len(outcomes) == 1  # no duplicate DecisionV2Outcome row was created

    reloaded = verify.query(DecisionV2Snapshot).filter_by(id=snapshot_id).one()
    assert reloaded.decision == original_values["decision"]
    assert float(reloaded.current_price) == original_values["current_price"]
    assert float(reloaded.target_1) == original_values["target_1"]
    assert float(reloaded.target_2) == original_values["target_2"]
    assert float(reloaded.target_3) == original_values["target_3"]
    assert float(reloaded.stop_loss) == original_values["stop_loss"]
    assert reloaded.decision_timestamp == original_values["decision_timestamp"]
    verify.close()
