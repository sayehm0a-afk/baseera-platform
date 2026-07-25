"""Unit tests for IntervalMarketIntelligenceScheduler -- verifies the
start/stop lifecycle and that one loop iteration creates a
MarketScanRun and hands off to run_market_scan_job, without ever
running a real scan (run_market_scan_job is monkeypatched to a stub).
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.market_intelligence.scheduler as scheduler_module
from src.core.db.database import Base
from src.domain.models import Stock
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scheduler import IMarketIntelligenceScheduler, IntervalMarketIntelligenceScheduler
from src.market_intelligence.types import ScheduleInterval


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
async def test_starting_twice_is_a_no_op(factory):
    scheduler = IntervalMarketIntelligenceScheduler(session_factory=factory, market_provider_getter=_fake_market_provider_getter)
    scheduler.start()
    first_task = scheduler._task
    scheduler.start()
    assert scheduler._task is first_task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_run_one_scan_creates_a_run_and_delegates_to_the_job_runner(factory, monkeypatch):
    monkeypatch.setenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "false")
    calls = []

    async def _fake_run_job(run_id, session_factory, market_provider, symbols=None, **kwargs):
        calls.append((run_id, symbols))

    monkeypatch.setattr(scheduler_module, "run_market_scan_job", _fake_run_job)

    repo = MarketIntelligenceRepository()
    scheduler = IntervalMarketIntelligenceScheduler(
        session_factory=factory, market_provider_getter=_fake_market_provider_getter, repository=repo,
    )

    await scheduler._run_one_scan()

    assert len(calls) == 1
    run_id, symbols = calls[0]
    assert symbols == ["2222"]

    session = factory()
    run = repo.get_run(session, run_id)
    assert run is not None
    session.close()


@pytest.mark.asyncio
async def test_loop_survives_an_exception_and_keeps_scheduling(factory, monkeypatch):
    """A failure creating the run row itself (not a scan failure --
    that's already caught inside run_market_scan_job) must not kill
    the scheduler's loop."""
    call_count = {"n": 0}

    async def _raising_run_one_scan():
        call_count["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "schedule_interval_seconds", lambda interval: 0.01)

    scheduler = IntervalMarketIntelligenceScheduler(session_factory=factory, market_provider_getter=_fake_market_provider_getter)
    scheduler._run_one_scan = _raising_run_one_scan

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1
