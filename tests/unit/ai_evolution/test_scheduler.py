"""Unit tests for OutcomeEvaluationScheduler and PatternDiscoveryScheduler
-- verifies the start/stop lifecycle and that one loop iteration hands
off to the underlying job function, without ever needing real forward
price data or real outcome history.
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.ai_evolution.scheduler as scheduler_module
import src.market_intelligence.scheduler_leader_lock as leader_lock_module
from src.ai_evolution.scheduler import (
    DailyIntelligenceAggregationScheduler,
    DailyReflectionScheduler,
    DecisionV2OutcomeScheduler,
    IOutcomeEvaluationScheduler,
    OutcomeEvaluationScheduler,
    PatternDiscoveryScheduler,
)
from src.core.db.database import Base
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _no_real_shared_redis(monkeypatch):
    """Isolates every test in this file from any real, process-wide
    shared Redis client -- DecisionV2OutcomeScheduler's default
    leader_lock would otherwise reach for a real Redis connection (and,
    across a real Redis instance shared by CI, a stale lease key left
    over from a previous test run), making leadership -- and therefore
    whether a monkeypatched _run_one_cycle actually gets called --
    nondeterministic. Mirrors tests/unit/market_data/ingestion/
    test_scheduler_leadership.py's identical fixture."""
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)


class _FakeRedis:
    """In-memory stand-in for redis.Redis -- covers exactly the
    operations SchedulerLeaderLock uses. Guarantees deterministic
    leadership for tests that need a scheduler to actually run its
    cycle, independent of whether a real Redis happens to be reachable.
    """

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


def test_satisfies_the_scheduler_protocol():
    scheduler = OutcomeEvaluationScheduler()
    assert isinstance(scheduler, IOutcomeEvaluationScheduler)


def test_is_not_running_before_start():
    scheduler = OutcomeEvaluationScheduler()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle(factory):
    scheduler = OutcomeEvaluationScheduler(session_factory=factory, interval_seconds=60)
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_starting_twice_is_a_no_op(factory):
    scheduler = OutcomeEvaluationScheduler(session_factory=factory, interval_seconds=60)
    scheduler.start()
    first_task = scheduler._task
    scheduler.start()
    assert scheduler._task is first_task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_run_one_cycle_delegates_to_evaluate_due_outcomes(factory, monkeypatch):
    calls = []

    def _fake_evaluate(session):
        calls.append(session)
        from src.ai_evolution.outcome_evaluation import OutcomeEvaluationSummary

        return OutcomeEvaluationSummary(evaluated=0, expired_no_data=0, skipped_pending=0)

    monkeypatch.setattr(scheduler_module, "evaluate_due_outcomes", _fake_evaluate)

    scheduler = OutcomeEvaluationScheduler(session_factory=factory, interval_seconds=60)
    await scheduler._run_one_cycle()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_loop_survives_an_exception_and_keeps_scheduling(factory):
    call_count = {"n": 0}

    async def _raising_run_one_cycle():
        call_count["n"] += 1
        raise RuntimeError("boom")

    scheduler = OutcomeEvaluationScheduler(session_factory=factory, interval_seconds=0.01)
    scheduler._run_one_cycle = _raising_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


# --- PatternDiscoveryScheduler --------------------------------------------


def test_pattern_discovery_scheduler_is_not_running_before_start():
    scheduler = PatternDiscoveryScheduler()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_pattern_discovery_scheduler_start_and_stop_lifecycle(factory):
    scheduler = PatternDiscoveryScheduler(session_factory=factory, interval_seconds=60)
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_pattern_discovery_scheduler_run_one_cycle_delegates_to_discover_patterns(factory, monkeypatch):
    calls = []

    def _fake_discover(session, **kwargs):
        calls.append(session)
        return []

    monkeypatch.setattr(scheduler_module, "discover_patterns", _fake_discover)

    scheduler = PatternDiscoveryScheduler(session_factory=factory, interval_seconds=60)
    await scheduler._run_one_cycle()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_pattern_discovery_scheduler_loop_survives_an_exception(factory):
    call_count = {"n": 0}

    async def _raising_run_one_cycle():
        call_count["n"] += 1
        raise RuntimeError("boom")

    scheduler = PatternDiscoveryScheduler(session_factory=factory, interval_seconds=0.01)
    scheduler._run_one_cycle = _raising_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


# --- DailyReflectionScheduler ----------------------------------------------


def test_daily_reflection_scheduler_is_not_running_before_start():
    scheduler = DailyReflectionScheduler()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_daily_reflection_scheduler_start_and_stop_lifecycle(factory):
    scheduler = DailyReflectionScheduler(session_factory=factory, interval_seconds=60)
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_daily_reflection_scheduler_run_one_cycle_delegates_to_generate_daily_reflection(factory, monkeypatch):
    calls = []

    def _fake_generate(session, **kwargs):
        calls.append(session)
        from datetime import date

        from src.domain.models import ReflectionReport

        return ReflectionReport(
            review_date=date(2026, 1, 1), recommendations_reviewed=0, successful_count=0,
            failed_count=0, partial_count=0, expired_count=0, key_findings=[], improvement_suggestions=[],
        )

    monkeypatch.setattr(scheduler_module, "generate_daily_reflection", _fake_generate)

    scheduler = DailyReflectionScheduler(session_factory=factory, interval_seconds=60)
    await scheduler._run_one_cycle()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_daily_reflection_scheduler_loop_survives_an_exception(factory):
    call_count = {"n": 0}

    async def _raising_run_one_cycle():
        call_count["n"] += 1
        raise RuntimeError("boom")

    scheduler = DailyReflectionScheduler(session_factory=factory, interval_seconds=0.01)
    scheduler._run_one_cycle = _raising_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


# --- DailyIntelligenceAggregationScheduler ----------------------------------


def test_daily_intelligence_aggregation_scheduler_is_not_running_before_start():
    scheduler = DailyIntelligenceAggregationScheduler()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_daily_intelligence_aggregation_scheduler_start_and_stop_lifecycle(factory):
    scheduler = DailyIntelligenceAggregationScheduler(session_factory=factory, interval_seconds=60)
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_daily_intelligence_aggregation_scheduler_run_one_cycle_delegates_to_aggregate(factory, monkeypatch):
    calls = []

    def _fake_aggregate(session, **kwargs):
        calls.append(session)
        from datetime import date

        from src.domain.models import DailyIntelligenceSnapshot

        return DailyIntelligenceSnapshot(
            snapshot_date=date(2026, 1, 1), recommendations_evaluated=0, successful_count=0,
            failed_count=0, partial_count=0, expired_count=0, agent_panel_snapshot_count=0, agent_debate_count=0,
        )

    monkeypatch.setattr(scheduler_module, "aggregate_daily_intelligence", _fake_aggregate)

    scheduler = DailyIntelligenceAggregationScheduler(session_factory=factory, interval_seconds=60)
    await scheduler._run_one_cycle()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_daily_intelligence_aggregation_scheduler_loop_survives_an_exception(factory):
    call_count = {"n": 0}

    async def _raising_run_one_cycle():
        call_count["n"] += 1
        raise RuntimeError("boom")

    scheduler = DailyIntelligenceAggregationScheduler(session_factory=factory, interval_seconds=0.01)
    scheduler._run_one_cycle = _raising_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


# --- DecisionV2OutcomeScheduler (M10) ---------------------------------------


def test_decision_v2_outcome_scheduler_is_not_running_before_start():
    scheduler = DecisionV2OutcomeScheduler()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_decision_v2_outcome_scheduler_start_and_stop_lifecycle(factory):
    scheduler = DecisionV2OutcomeScheduler(session_factory=factory, interval_seconds=60)
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_decision_v2_outcome_scheduler_run_one_cycle_delegates_to_evaluate_pending_outcomes(
    factory, monkeypatch
):
    calls = []

    def _fake_evaluate(session, **kwargs):
        calls.append(session)
        from src.ai_evolution.decision_v2_outcome_evaluation import DecisionV2OutcomeEvaluationSummary

        return DecisionV2OutcomeEvaluationSummary(
            evaluated_terminal=0, still_pending=0, data_unavailable=0, cancelled=0
        )

    monkeypatch.setattr(scheduler_module, "evaluate_pending_outcomes", _fake_evaluate)

    scheduler = DecisionV2OutcomeScheduler(session_factory=factory, interval_seconds=60)
    await scheduler._run_one_cycle()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_decision_v2_outcome_scheduler_loop_survives_an_exception(factory):
    call_count = {"n": 0}

    async def _raising_run_one_cycle():
        call_count["n"] += 1
        raise RuntimeError("boom")

    scheduler = DecisionV2OutcomeScheduler(
        session_factory=factory,
        interval_seconds=0.01,
        leader_lock=SchedulerLeaderLock(
            redis_client=_FakeRedis(), lease_key="basirah:decision_v2_outcome_scheduler:leader:test"
        ),
    )
    scheduler._run_one_cycle = _raising_run_one_cycle

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1


@pytest.mark.asyncio
async def test_decision_v2_outcome_scheduler_non_leader_never_runs_a_cycle(factory, monkeypatch):
    """A follower (not holding the decision-v2-outcome-scheduler lease)
    must never call evaluate_pending_outcomes -- zero DB work, only the
    skip counter moves. Mirrors IngestionScheduler's TEST2."""
    scheduler = DecisionV2OutcomeScheduler(session_factory=factory, interval_seconds=999999)
    assert scheduler.is_leader is False  # never started -- default not-leader

    calls = {"n": 0}

    async def _counting_run_one_cycle():
        calls["n"] += 1

    scheduler._run_one_cycle = _counting_run_one_cycle

    async def _recording_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop()

    assert calls["n"] == 0
    assert scheduler.skipped_due_to_not_leader_count == 1
