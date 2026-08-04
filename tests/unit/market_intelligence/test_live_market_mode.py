"""Unit tests for LiveMarketModeScheduler -- fake, lightweight
start-stoppable doubles for the inner IngestionScheduler/
IntervalMarketIntelligenceScheduler (neither one is real/DB-backed
here; each is independently tested in its own module), plus an
injected clock so market-open/closed transitions are deterministic
and don't depend on real wall-clock time.
"""

from datetime import datetime

import pytest

from src.market_intelligence.live_market_mode import LiveMarketModeScheduler
from src.market_intelligence.trading_calendar import TADAWUL_TIMEZONE


class _FakeStartStoppable:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self._running = False

    def start(self):
        self.start_calls += 1
        self._running = True

    async def stop(self):
        self.stop_calls += 1
        self._running = False

    @property
    def is_running(self):
        return self._running


def _open_moment():
    # 2026-07-28 is a Tuesday -- a Tadawul trading day, mid-session.
    return datetime(2026, 7, 28, 12, 0, tzinfo=TADAWUL_TIMEZONE)


def _closed_moment():
    # 2026-07-31 is a Friday -- Tadawul does not trade.
    return datetime(2026, 7, 31, 12, 0, tzinfo=TADAWUL_TIMEZONE)


def _make_scheduler(clock_value):
    ingestion = _FakeStartStoppable()
    scan = _FakeStartStoppable()
    scheduler = LiveMarketModeScheduler(
        ingestion_scheduler=ingestion,
        market_intelligence_scheduler=scan,
        clock=lambda: clock_value,
        poll_interval_seconds=0.01,
    )
    return scheduler, ingestion, scan


def test_is_not_running_before_start():
    scheduler, _, _ = _make_scheduler(_closed_moment())
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle():
    scheduler, _, _ = _make_scheduler(_closed_moment())
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_starting_twice_is_a_no_op():
    scheduler, _, _ = _make_scheduler(_closed_moment())
    scheduler.start()
    first_task = scheduler._task
    scheduler.start()
    assert scheduler._task is first_task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_tick_starts_inner_schedulers_when_market_opens():
    scheduler, ingestion, scan = _make_scheduler(_open_moment())
    assert ingestion.start_calls == 0

    await scheduler._tick()

    assert ingestion.start_calls == 1
    assert scan.start_calls == 1
    assert scheduler.is_market_currently_open is True


@pytest.mark.asyncio
async def test_tick_does_not_restart_already_running_schedulers():
    scheduler, ingestion, scan = _make_scheduler(_open_moment())
    await scheduler._tick()
    await scheduler._tick()
    await scheduler._tick()

    assert ingestion.start_calls == 1
    assert scan.start_calls == 1


@pytest.mark.asyncio
async def test_tick_stops_inner_schedulers_when_market_closes():
    scheduler, ingestion, scan = _make_scheduler(_open_moment())
    await scheduler._tick()
    assert ingestion.is_running is True

    scheduler._clock = lambda: _closed_moment()
    await scheduler._tick()

    assert ingestion.stop_calls == 1
    assert scan.stop_calls == 1
    assert scheduler.is_market_currently_open is False


@pytest.mark.asyncio
async def test_tick_while_market_stays_closed_never_starts_anything():
    scheduler, ingestion, scan = _make_scheduler(_closed_moment())
    await scheduler._tick()
    await scheduler._tick()

    assert ingestion.start_calls == 0
    assert scan.start_calls == 0


@pytest.mark.asyncio
async def test_stop_also_stops_still_running_inner_schedulers():
    scheduler, ingestion, scan = _make_scheduler(_open_moment())
    scheduler.start()
    await scheduler._tick()  # deterministically run one tick instead of racing the poll loop
    assert ingestion.is_running is True

    await scheduler.stop()

    assert ingestion.stop_calls >= 1
    assert scan.stop_calls >= 1
    assert scheduler.is_market_currently_open is False


@pytest.mark.asyncio
async def test_loop_survives_an_exception_and_keeps_polling(monkeypatch):
    import src.market_intelligence.live_market_mode as live_market_mode_module

    call_count = {"n": 0}

    def _raising_is_market_open(_now):
        call_count["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(live_market_mode_module, "is_market_open", _raising_is_market_open)

    scheduler, _, _ = _make_scheduler(_open_moment())
    scheduler.start()
    import asyncio

    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1
