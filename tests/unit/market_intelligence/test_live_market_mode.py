"""Unit tests for LiveMarketModeScheduler -- a fake, lightweight
start-stoppable double for the inner IntervalMarketIntelligenceScheduler
(not real/DB-backed here; independently tested in its own module),
plus an injected clock so market-open/closed transitions are
deterministic and don't depend on real wall-clock time.

The ingestion scheduler (symbols/historical_ohlcv/fundamentals/
dividends backfill) is deliberately NOT exercised here: it is no
longer owned or market-hours-gated by LiveMarketModeScheduler (see
live_market_mode.py's module docstring for the production gap this
fixed) -- it always runs on its own schedule via main.py's own
INGESTION_SCHEDULER_ENABLED-gated wiring, tested independently in
tests/unit/market_data/ingestion/test_scheduler.py.
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
    scan = _FakeStartStoppable()
    scheduler = LiveMarketModeScheduler(
        market_intelligence_scheduler=scan,
        clock=lambda: clock_value,
        poll_interval_seconds=0.01,
    )
    return scheduler, scan


def test_is_not_running_before_start():
    scheduler, _ = _make_scheduler(_closed_moment())
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle():
    scheduler, _ = _make_scheduler(_closed_moment())
    scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_starting_twice_is_a_no_op():
    scheduler, _ = _make_scheduler(_closed_moment())
    scheduler.start()
    first_task = scheduler._task
    scheduler.start()
    assert scheduler._task is first_task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_tick_starts_inner_scheduler_when_market_opens():
    scheduler, scan = _make_scheduler(_open_moment())
    assert scan.start_calls == 0

    await scheduler._tick()

    assert scan.start_calls == 1
    assert scheduler.is_market_currently_open is True


@pytest.mark.asyncio
async def test_tick_does_not_restart_already_running_scheduler():
    scheduler, scan = _make_scheduler(_open_moment())
    await scheduler._tick()
    await scheduler._tick()
    await scheduler._tick()

    assert scan.start_calls == 1


@pytest.mark.asyncio
async def test_tick_stops_inner_scheduler_when_market_closes():
    scheduler, scan = _make_scheduler(_open_moment())
    await scheduler._tick()
    assert scan.is_running is True

    scheduler._clock = lambda: _closed_moment()
    await scheduler._tick()

    assert scan.stop_calls == 1
    assert scheduler.is_market_currently_open is False


@pytest.mark.asyncio
async def test_tick_while_market_stays_closed_never_starts_anything():
    scheduler, scan = _make_scheduler(_closed_moment())
    await scheduler._tick()
    await scheduler._tick()

    assert scan.start_calls == 0


@pytest.mark.asyncio
async def test_stop_also_stops_still_running_inner_scheduler():
    scheduler, scan = _make_scheduler(_open_moment())
    scheduler.start()
    await scheduler._tick()  # deterministically run one tick instead of racing the poll loop
    assert scan.is_running is True

    await scheduler.stop()

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

    scheduler, _ = _make_scheduler(_open_moment())
    scheduler.start()
    import asyncio

    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count["n"] >= 1
