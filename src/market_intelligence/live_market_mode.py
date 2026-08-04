"""Live Market Mode: a single top-level toggle that runs Basirah's
existing ingestion + market-scan schedulers only while the Tadawul
market is actually open (see trading_calendar.py), instead of on a
fixed interval around the clock.

Deliberately a thin supervisor, not a third implementation of
ingestion/scanning: `LiveMarketModeScheduler` owns one
`IngestionScheduler` and one `IntervalMarketIntelligenceScheduler` --
both already real, both already independently tested -- and only
decides *when* to `start()`/`stop()` them. Every guarantee those two
schedulers already provide carries over unchanged and is not
reimplemented here:
  - Storage is dedup-safe because `RecommendationSnapshot`'s and
    `SymbolIntelligenceRecord`'s own unique constraints are (E1's
    `save_symbol_records` and each ingestion job's own upsert), not
    anything this module adds.
  - Job loops never overlap themselves (each scheduler's own
    "run then sleep" structure).
  - Failures are retried/logged by each scheduler's own existing
    machinery.

This module's only new behavior is the market-hours gate: a cheap
(no network I/O) supervisor tick, on `LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS`,
that starts both inner schedulers the moment the Tadawul session opens
and stops them the moment it closes -- so an unattended deployment
never spends SAHMK requests or DB writes outside trading hours, and
resumes automatically at the next session open without an operator
action.

Disabled by default (`LIVE_MARKET_MODE_ENABLED=false`), the same
secure/inert-by-default posture every other scheduler in this codebase
uses. Deliberately NOT combined with the standalone
`INGESTION_SCHEDULER_ENABLED`/`MARKET_INTELLIGENCE_SCHEDULER_ENABLED`
flags in main.py's wiring -- Live Market Mode is meant to replace
those two always-on schedulers, not run alongside them (running both
would just double the API calls against the same symbols with no
benefit).
"""

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol, runtime_checkable

from src.market_data.ingestion.scheduler import IngestionScheduler
from src.market_intelligence.config import get_live_market_mode_poll_interval_seconds
from src.market_intelligence.scheduler import IntervalMarketIntelligenceScheduler
from src.market_intelligence.trading_calendar import is_market_open

logger = logging.getLogger(__name__)


@runtime_checkable
class _StartStoppable(Protocol):
    """The three-member shape both `IngestionScheduler` and
    `IntervalMarketIntelligenceScheduler` already satisfy -- lets
    tests inject a lightweight fake instead of the real, DB/network-
    touching schedulers."""

    def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    @property
    def is_running(self) -> bool:
        ...


class LiveMarketModeScheduler:
    def __init__(
        self,
        ingestion_scheduler: Optional[_StartStoppable] = None,
        market_intelligence_scheduler: Optional[_StartStoppable] = None,
        clock: Optional[Callable[[], datetime]] = None,
        poll_interval_seconds: Optional[float] = None,
    ):
        self._ingestion_scheduler: _StartStoppable = ingestion_scheduler or IngestionScheduler()
        self._market_intelligence_scheduler: _StartStoppable = (
            market_intelligence_scheduler or IntervalMarketIntelligenceScheduler()
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._poll_interval_seconds = (
            poll_interval_seconds if poll_interval_seconds is not None else get_live_market_mode_poll_interval_seconds()
        )
        self._task: Optional[asyncio.Task] = None
        self._market_was_open = False

    @property
    def is_running(self) -> bool:
        return self._task is not None

    @property
    def is_market_currently_open(self) -> bool:
        """The supervisor's last-observed state (updated once per
        poll), not a forced fresh read -- cheap enough for a
        health/status endpoint to read without side effects."""
        return self._market_was_open

    def start(self) -> None:
        if self._task is not None:
            logger.warning("LiveMarketModeScheduler.start() called while already running -- ignoring.")
            return
        self._task = asyncio.ensure_future(self._loop())
        logger.info("Live Market Mode supervisor started (Tadawul-hours-gated, poll=%.0fs).", self._poll_interval_seconds)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._ingestion_scheduler.is_running:
            await self._ingestion_scheduler.stop()
        if self._market_intelligence_scheduler.is_running:
            await self._market_intelligence_scheduler.stop()
        self._market_was_open = False
        logger.info("Live Market Mode supervisor stopped.")

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in Live Market Mode supervisor tick.")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _tick(self) -> None:
        open_now = is_market_open(self._clock())
        if open_now and not self._market_was_open:
            logger.info("Live Market Mode: Tadawul session opened -- starting ingestion + scan schedulers.")
            self._ingestion_scheduler.start()
            self._market_intelligence_scheduler.start()
        elif not open_now and self._market_was_open:
            logger.info("Live Market Mode: Tadawul session closed -- stopping ingestion + scan schedulers.")
            await self._ingestion_scheduler.stop()
            await self._market_intelligence_scheduler.stop()
        self._market_was_open = open_now
