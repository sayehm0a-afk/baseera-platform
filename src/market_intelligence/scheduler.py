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

2026-08-13 SAHMK quota-exhaustion incident -- root causes fixed here:
  1. `_run_one_cycle` (formerly `_run_one_scan`) now runs under
     `priority_scope(BACKGROUND)`. It previously ran unmarked, which
     defaults to CRITICAL priority (see request_priority.py) -- the
     one caller responsible for the overwhelming majority of daily
     SAHMK volume was never subject to `reserved_for_critical`'s
     throttle at all, defeating the reserve's entire purpose.
  2. `main.py`'s `@app.on_event("startup")` runs independently in
     every one of Gunicorn's worker processes (Dockerfile: `--workers
     4`), so `LiveMarketModeScheduler`/this scheduler's own `start()`
     ran four times, each driving its own full, redundant scan loop
     against the identical symbol universe. `_leader_lock` (Redis
     SETNX-with-TTL, see scheduler_leader_lock.py) now gates the
     actual scan work so only one worker performs it at a time.
  3. Every cycle re-selected the ENTIRE active universe (372 symbols
     in production), each issuing a live SAHMK quote call with only a
     15s cache TTL -- no benefit at this cadence. `_run_one_cycle` now
     selects a bounded, config-driven batch via Radar V2's own Stage 1
     (see point 6 below), so the full universe still gets evaluated
     every cycle at zero SAHMK cost, but only a capped, ranked subset
     ever reaches a live SAHMK call.
  4. No overlap guard existed between cycles/workers at all (unlike
     POST /market/scan and the admin diagnostic-scan route, which
     both already checked this) -- `has_in_flight_run` now gates a new
     cycle the same way.
  5. No quota-health circuit breaker existed -- a cycle would only
     discover the quota was low via a failed mid-scan acquire() call,
     after already wasting whatever partial work preceded it. A new
     cycle now checks `get_default_rate_limiter().get_status()` first
     and skips entirely (zero SAHMK calls) if background-eligible
     quota is low or upstream-confirmed-exhausted.

2026-08-18 real-market validation audit finding, fixed here: this
  scheduler used to select its per-cycle batch itself
  (`SymbolSelector.select(prioritize_stale=True)`, oldest-scanned-first,
  no ranking) and write only `MarketScanRun`/`DecisionV2Snapshot` rows --
  never a `RadarOpportunity` row. The consumer-facing Radar page
  (`GET /api/v1/radar/summary`) reads exclusively from
  `RadarOpportunity`, which was otherwise populated only by the
  admin-only `POST /admin/market-intelligence/radar-v2/scan` -- never
  invoked automatically, so a real user's Radar was always empty.
  `_run_one_cycle` now delegates symbol selection and the full
  Stage 1 (zero-cost local ranking) -> Stage 2 (bounded live
  validation) -> `RadarOpportunity` emission pass to
  `run_radar_v2_cycle` (see `radar_v2.py`), via `_stage2_runner` below
  as the injected Stage 2 callable -- reusing the identical
  `run_market_scan_job`/`MarketScanRun` machinery this module already
  used, so `MarketScanRun`/`DecisionV2Snapshot` rows and every existing
  safety guard in this file are unchanged; only symbol selection
  (ranked Stage 1 candidates instead of stale-first) and the addition
  of a final `RadarOpportunity` emission step are new.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter, get_default_rate_limiter
from src.market_data.sahmk.operation_scope import RADAR_V2, operation_scope
from src.market_data.sahmk.request_priority import BACKGROUND, priority_scope
from src.market_intelligence.config import (
    get_market_intelligence_scan_interval,
    get_max_scan_run_duration_hours,
    get_scan_leader_lease_seconds,
    get_scan_min_background_quota_remaining,
    schedule_interval_seconds,
)
from src.market_intelligence.radar_v2 import run_radar_v2_cycle as _real_run_radar_v2_cycle
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock
from src.market_intelligence.services.scan_job_runner import run_market_scan_job
from src.market_intelligence.types import ScheduleInterval

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SchedulerStage2Result:
    """Satisfies the same minimal shape `run_radar_v2_cycle`'s injected
    Stage 2 runner must return (`.executed`/`.stop_reason`/`.run_id`;
    see `radar_v2.StageTwoRunner`) -- a scheduler-local double of
    `ContinueScanCycleOut`, not that Pydantic API schema itself, since
    this module has no reason to depend on `src.api.*`."""

    executed: bool
    stop_reason: Optional[str] = None
    run_id: Optional[int] = None


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
        leader_lock: Optional[SchedulerLeaderLock] = None,
        rate_limiter: Optional[SahmkRateLimiter] = None,
        run_radar_v2_cycle: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._get_market_provider = market_provider_getter or self._default_market_provider_getter
        self._interval = interval or get_market_intelligence_scan_interval()
        self._repository = repository or MarketIntelligenceRepository()
        self._leader_lock = leader_lock or SchedulerLeaderLock()
        self._rate_limiter = rate_limiter or get_default_rate_limiter()
        self._run_radar_v2_cycle = run_radar_v2_cycle or _real_run_radar_v2_cycle
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
        requiring an operator to notice and manually clear it. Zero
        SAHMK cost (a DB-only operation) -- safe to run from every
        worker regardless of scan-loop leadership."""
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
        self._leader_lock.release()
        logger.info("MarketIntelligenceScheduler stopped.")

    async def _loop(self) -> None:
        interval_seconds = schedule_interval_seconds(self._interval)
        lease_seconds = get_scan_leader_lease_seconds()
        while True:
            try:
                if self._leader_lock.try_acquire_or_renew(lease_seconds):
                    await self._run_one_cycle()
                else:
                    logger.debug("MarketIntelligenceScheduler: not scan-loop leader this tick -- skipping.")
            except asyncio.CancelledError:
                raise
            except Exception:
                # run_market_scan_job already catches and records its own
                # failures -- reaching here means creating the run row
                # itself failed, a DB-layer problem. Logged, not raised,
                # so the loop keeps running on schedule.
                logger.exception("Unexpected error running a scheduled market scan cycle.")
            await asyncio.sleep(interval_seconds)

    def _quota_allows_a_new_cycle(self) -> bool:
        """Circuit breaker, checked before touching the DB or SAHMK at
        all this cycle -- see this module's own docstring for the
        2026-08-13 incident this closes. P0 remediation (independent
        PR #99 audit, P2 finding #2): reads
        remaining_today_for_background_after_live_scan_reserve, not the
        legacy remaining_today_for_background -- the legacy field does
        not account for the live-scan reserve, so this circuit breaker
        could otherwise let a cycle start that then hits
        SahmkQuotaReservedForLiveScanError partway through (caught and
        degraded gracefully per-symbol, but wastes a cycle it should
        have skipped proactively)."""
        status = self._rate_limiter.get_status()
        if status.get("upstream_confirmed_exhausted"):
            logger.warning(
                "MarketIntelligenceScheduler: SAHMK upstream quota is confirmed exhausted -- skipping this cycle."
            )
            return False
        remaining_bg = status.get("remaining_today_for_background_after_live_scan_reserve")
        threshold = get_scan_min_background_quota_remaining()
        if remaining_bg is not None and remaining_bg < threshold:
            logger.warning(
                "MarketIntelligenceScheduler: background-eligible SAHMK quota low (%s remaining, "
                "threshold %s) -- skipping this cycle to protect the reserve.",
                remaining_bg, threshold,
            )
            return False
        return True

    async def _stage2_runner(
        self, session: Session, caller: str, resolve_symbols: Callable[[], List[str]]
    ) -> _SchedulerStage2Result:
        """The `radar_v2.StageTwoRunner` this scheduler injects into
        `run_radar_v2_cycle` -- Stage 1 (inside `run_radar_v2_cycle`,
        zero SAHMK cost) has already picked and capped the candidate
        list by the time this is called, so this only needs to do what
        `_run_one_cycle` always did once it had a symbol list: create
        the `MarketScanRun` row and hand off to `run_market_scan_job`,
        under `operation_scope(RADAR_V2)` instead of `MARKET_SCAN` so
        this cycle's SAHMK usage is separately attributable (see
        `GET .../radar-v2/sahmk-consumption`). `caller` is accepted only
        to satisfy `StageTwoRunner`'s shape (unused -- nothing here logs
        it; `_run_one_bounded_background_cycle` is the caller that
        actually uses it, for its own manually-triggered routes)."""
        symbols = resolve_symbols()
        if not symbols:
            return _SchedulerStage2Result(executed=False, stop_reason="no_candidates")

        run = self._repository.create_scan_run(session, symbols_requested=len(symbols))
        run_id = run.id

        with priority_scope(BACKGROUND), operation_scope(RADAR_V2):
            provider = await self._get_market_provider()
            await run_market_scan_job(run_id, self._session_factory, provider, symbols=symbols)

        # `run_market_scan_job` wrote its DecisionV2Snapshot rows through
        # its own session (via `self._session_factory`, not `session`);
        # this scheduler's own outer `session` must see them fresh
        # before `run_radar_v2_cycle`'s emit step queries by scan_run_id
        # right after this returns -- the same reasoning
        # `_run_one_bounded_background_cycle` documents for its own
        # `session.expire_all()` call.
        session.expire_all()
        return _SchedulerStage2Result(executed=True, run_id=run_id)

    async def _run_one_cycle(self) -> None:
        if not self._quota_allows_a_new_cycle():
            return

        session = self._session_factory()
        try:
            self._repository.reap_stale_runs(session, get_max_scan_run_duration_hours())
            in_flight = self._repository.has_in_flight_run(session)
            if in_flight is not None:
                logger.info(
                    "MarketIntelligenceScheduler: a scan (run %d, %s) is already in progress -- "
                    "skipping this cycle.",
                    in_flight.id, in_flight.status.value,
                )
                return

            result = await self._run_radar_v2_cycle(session, self._stage2_runner)

            if result.stage2_executed:
                logger.info(
                    "MarketIntelligenceScheduler: Radar V2 cycle complete (scan run %s) -- "
                    "%d candidate(s) from a %d-symbol universe, %d opportunity(ies) emitted, "
                    "%d suppressed as duplicate.",
                    result.scan_run_id, result.stage1_candidate_count, result.stage1_universe_size,
                    len(result.opportunities_emitted), len(result.opportunities_suppressed_as_duplicate),
                )
            elif result.stage2_stop_reason:
                logger.info(
                    "MarketIntelligenceScheduler: Radar V2 cycle did not execute Stage 2 this tick (%s).",
                    result.stage2_stop_reason,
                )
        finally:
            session.close()
