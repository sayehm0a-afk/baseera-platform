"""Live Market Mode: a single top-level toggle that runs Basirah's
market-scan scheduler only while the Tadawul market is actually open
(see trading_calendar.py), instead of on a fixed interval around the
clock.

Deliberately a thin supervisor, not a third implementation of
scanning: `LiveMarketModeScheduler` owns one
`IntervalMarketIntelligenceScheduler` -- already real, already
independently tested -- and only decides *when* to `start()`/`stop()`
it. Every guarantee that scheduler already provides carries over
unchanged and is not reimplemented here:
  - Storage is dedup-safe because `RecommendationSnapshot`'s and
    `SymbolIntelligenceRecord`'s own unique constraints are (E1's
    `save_symbol_records`), not anything this module adds.
  - The job loop never overlaps itself (the scheduler's own
    "run then sleep" structure).
  - Failures are retried/logged by the scheduler's own existing
    machinery.

This module's only new behavior is the market-hours gate: a cheap
(no network I/O) supervisor tick, on `LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS`,
that starts the inner scan scheduler the moment the Tadawul session
opens and stops it the moment it closes -- so an unattended deployment
never runs a full-market scan against stale/closed-session prices, and
resumes automatically at the next session open without an operator
action.

CORRECTION (production gap found 2026-08-08): this module previously
also owned an `IngestionScheduler` instance (symbols/historical_ohlcv/
fundamentals/dividends backfill) and gated it the same way -- but
those four jobs are periodic *maintenance*, not live intraday
quoting, and have no real reason to depend on the market being open;
a symbol's fundamentals or dividend history doesn't change because
Tadawul is closed. Gating them here meant that whenever
LIVE_MARKET_MODE_ENABLED=true (as it is in production) and the market
was closed (e.g. the Tadawul weekend), *zero* backfill ever ran
automatically -- confirmed live via GET /admin/system/summary showing
`ingestion_scheduler_running: false` with no scheduled runs, only ones
this session triggered manually via the admin full-discovery route.
`IngestionScheduler` is now started unconditionally by main.py
whenever `INGESTION_SCHEDULER_ENABLED=true`, independent of both Live
Market Mode and market hours -- see main.py's startup wiring. This
module keeps gating only the market-scan scheduler, which genuinely is
market-hours-sensitive (a scan is meant to reflect the live session).

Disabled by default (`LIVE_MARKET_MODE_ENABLED=false`), the same
secure/inert-by-default posture every other scheduler in this codebase
uses. Deliberately NOT combined with the standalone
`MARKET_INTELLIGENCE_SCHEDULER_ENABLED` flag in main.py's wiring --
Live Market Mode is meant to replace that always-on scan scheduler,
not run alongside it (running both would just double the API calls
against the same symbols with no benefit). `INGESTION_SCHEDULER_ENABLED`
is independent of this flag entirely (see the correction above).
"""

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol, runtime_checkable

from src.market_intelligence.config import get_live_market_mode_poll_interval_seconds
from src.market_intelligence.scheduler import IntervalMarketIntelligenceScheduler
from src.market_intelligence.trading_calendar import is_market_open

logger = logging.getLogger(__name__)


@runtime_checkable
class _StartStoppable(Protocol):
    """The three-member shape `IntervalMarketIntelligenceScheduler`
    already satisfies -- lets tests inject a lightweight fake instead
    of the real, DB/network-touching scheduler."""

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
        market_intelligence_scheduler: Optional[_StartStoppable] = None,
        clock: Optional[Callable[[], datetime]] = None,
        poll_interval_seconds: Optional[float] = None,
    ):
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
            logger.info("Live Market Mode: Tadawul session opened -- starting market-scan scheduler.")
            self._market_intelligence_scheduler.start()
        elif not open_now and self._market_was_open:
            logger.info("Live Market Mode: Tadawul session closed -- stopping market-scan scheduler.")
            await self._market_intelligence_scheduler.stop()
        self._market_was_open = open_now
