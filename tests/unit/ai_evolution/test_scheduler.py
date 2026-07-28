"""Unit tests for OutcomeEvaluationScheduler -- verifies the start/stop
lifecycle and that one loop iteration hands off to
evaluate_due_outcomes, without ever needing real forward price data.
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.ai_evolution.scheduler as scheduler_module
from src.ai_evolution.scheduler import IOutcomeEvaluationScheduler, OutcomeEvaluationScheduler
from src.core.db.database import Base


@pytest.fixture
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


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
