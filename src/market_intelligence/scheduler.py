"""MarketIntelligenceScheduler: recurring, unattended market scans --
the same "one asyncio.Task, run then sleep(interval), never overlap
itself" design `src.market_data.ingestion.scheduler.IngestionScheduler`
already established, applied to `run_market_scan_job` instead of an
ingestion job. Reuses that job runner rather than re-implementing scan
execution.

`IMarketIntelligenceScheduler` is the small interface
`IntervalMarketIntelligenceScheduler` (the only implementation in this
codebase) satisfies -- "the scheduler must be replaceable" means any
future implementation (a cron-backed one, a message-queue-triggered
one) only needs to satisfy this same three-member shape to be a
drop-in replacement in main.py's startup/shutdown wiring.

Disabled by default (`MARKET_INTELLIGENCE_SCHEDULER_ENABLED=false`) --
the same secure/inert-by-default posture `INGESTION_SCHEDULER_ENABLED`
already uses: an unattended, recurring full-market scan is real
workload an operator must opt into, not something that starts itself.
"""

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable, List, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_intelligence.config import (
    get_market_intelligence_scan_interval,
    get_max_scan_run_duration_hours,
    schedule_interval_seconds,
)
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.services.scan_job_runner import run_market_scan_job
from src.market_intelligence.symbol_selector import SymbolSelector
from src.market_intelligence.types import ScheduleInterval

logger = logging.getLogger(__name__)


@runtime_checkable
class IMarketIntelligenceScheduler(Protocol):
    def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    @property
    def is_running(self) -> bool:
        ...


class IntervalMarketIntelligenceScheduler:
    """The one concrete `IMarketIntelligenceScheduler` this codebase
    ships. `interval` defaults to `MARKET_INTELLIGENCE_SCAN_INTERVAL`
    (any `ScheduleInterval`: every minute, every 5 minutes, hourly,
    daily, weekly) -- passing one explicitly overrides the environment
    for this instance."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        market_provider_getter: Optional[Callable[[], Awaitable[IMarketDataProvider]]] = None,
        interval: Optional[ScheduleInterval] = None,
        repository: Optional[MarketIntelligenceRepository] = None,
        symbol_selector: Optional[SymbolSelector] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._get_market_provider = market_provider_getter or self._default_market_provider_getter
        self._interval = interval or get_market_intelligence_scan_interval()
        self._repository = repository or MarketIntelligenceRepository()
        self._symbol_selector = symbol_selector or SymbolSelector()
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @staticmethod
    async def _default_market_provider_getter() -> IMarketDataProvider:
        from src.market_data.provider_factory import get_market_data_provider

        return await get_market_data_provider()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self._task is not None:
            logger.warning("MarketIntelligenceScheduler.start() called while already running -- ignoring.")
            return
        self._reap_stale_runs_once()
        self._task = asyncio.ensure_future(self._loop())
        logger.info("MarketIntelligenceScheduler started (interval=%s).", self._interval.value)

    def _reap_stale_runs_once(self) -> None:
        """A process kill (Railway restart, OOM) between a scan's
        PENDING/RUNNING insert and its finish never reaches
        finish_run(), leaving a MarketScanRun row stuck RUNNING forever
        -- indistinguishable from a genuinely in-progress scan to
        POST /market/scan's own overlap guard, which would then block
        every future scan (scheduled or manual) permanently after a
        crash. Reaping once here, right before this scheduler starts
        scheduling new scans, closes that stale-lock window without
        requiring an operator to notice and manually clear it."""
        session = self._session_factory()
        try:
            reaped = self._repository.reap_stale_runs(session, get_max_scan_run_duration_hours())
            if reaped:
                logger.warning(
                    "MarketIntelligenceScheduler.start(): reaped %d stale MarketScanRun row(s) "
                    "(run id(s): %s) before scheduling.",
                    len(reaped),
                    [r.id for r in reaped],
                )
        finally:
            session.close()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("MarketIntelligenceScheduler stopped.")

    async def _loop(self) -> None:
        interval_seconds = schedule_interval_seconds(self._interval)
        while True:
            try:
                await self._run_one_scan()
            except asyncio.CancelledError:
                raise
            except Exception:
                # run_market_scan_job already catches and records its own
                # failures -- reaching here means creating the run row
                # itself failed, a DB-layer problem. Logged, not raised,
                # so the loop keeps running on schedule.
                logger.exception("Unexpected error running a scheduled market scan.")
            await asyncio.sleep(interval_seconds)

    async def _run_one_scan(self) -> None:
        provider = await self._get_market_provider()

        session = self._session_factory()
        try:
            symbols: List[str] = self._symbol_selector.select(session)
            run = self._repository.create_scan_run(session, symbols_requested=len(symbols))
            run_id = run.id
        finally:
            session.close()

        await run_market_scan_job(run_id, self._session_factory, provider, symbols=symbols)
