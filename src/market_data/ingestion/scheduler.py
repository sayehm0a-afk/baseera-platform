"""The ingestion scheduler: runs the four ingestion jobs (symbols,
historical OHLCV, fundamentals, dividends) on independent recurring
intervals, so the database stays synchronized with SAHMK automatically
once enabled (INGESTION_SCHEDULER_ENABLED=true).

Not built on src.core.runtime.task_queue.scheduler.Scheduler/IScheduler
-- that class only ever records `{task_id, delay}` in a dict; nothing
in this codebase reads that dict or fires anything from it. This is a
purpose-built async interval scheduler instead: one asyncio.Task per
job, each looping "run, then sleep(interval)" independently, so a slow
or failing job never blocks another job's schedule.

Each job run is:
  - Never overlapping with itself by construction: each job's loop is
    "await run, then await sleep(interval)," strictly sequential, so
    the next run cannot start until the previous one (including all of
    its own retries) has fully finished -- no lock is needed to
    prevent two concurrent runs of the same job, because the loop
    structure makes that impossible in the first place.
  - Retried at the job level (run_ingestion_job, exponential backoff)
    if the whole run raises -- distinct from SahmkClient's own
    per-request retry, this is about the *job* failing outright (a DB
    connection blip, an exception escaping the ingestion function's
    own per-symbol isolation), not a single request.
  - Logged twice: a structured log line (this process's normal
    logging) and a row in IngestionRunLog (durable, queryable) --
    execution time, symbols requested/succeeded/failed, rows upserted,
    and retry count, exactly as requested.

Idempotency, incremental updates, and duplicate prevention are NOT this
module's concern -- they're guaranteed one layer down, by each
ingestion job (get_or_create_stock, upsert_price_bar, PriceBar's/
FundamentalSnapshot's/Dividend's own unique constraints). This module
only decides *when* to call them and *what happened* when it did.

2026-08-17 SAHMK quota-waste root-cause fix: `main.py`'s
`@app.on_event("startup")` runs independently in every one of
Gunicorn's worker processes (Dockerfile: `--workers 4`), so
`IngestionScheduler.start()` ran four times, each driving its own full,
redundant set of the four job loops against the identical symbol
universe -- real production evidence the same day showed ~2.8x-3.6x
the expected per-symbol SAHMK call count for OHLCV/fundamentals/
dividends. `MarketIntelligenceScheduler` already closed the identical
2026-08-13 incident for the market-scan loop via a Redis-backed
`SchedulerLeaderLock`; `IngestionScheduler` never received the same
fix. `_leader_lock` (a second `SchedulerLeaderLock` instance, its own
independent lease key) now gates real job execution the same way: a
dedicated, fast heartbeat task (independent of any single job's own,
often much longer, interval) keeps `self._is_leader` current, and each
job loop skips its own tick's work entirely (zero SAHMK cost, no
`IngestionRunLog` row written) whenever this worker does not currently
hold the lease.
"""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Optional

from sqlalchemy.orm import Session

from src.core.db import database
from src.domain.models import IngestionJobStatus, IngestionRunLog, Stock
from src.market_data.ingestion import config as ingestion_config
from src.market_data.ingestion._common import IngestionResult
from src.market_data.ingestion.ingest_dividends import ingest_dividends
from src.market_data.ingestion.ingest_fundamentals import ingest_fundamentals
from src.market_data.ingestion.ingest_historical_ohlcv import ingest_historical_ohlcv
from src.market_data.ingestion.ingest_symbols import sync_symbols
from src.market_data.ingestion.outcome_tracking import pending_signal_symbols
from src.market_data.fundamental_provider_factory import get_fundamental_data_provider
from src.market_data.provider_factory import get_market_data_provider
from src.market_data.sahmk.rate_limiter import (
    SahmkRateLimitExceededError,
    SahmkUpstreamQuotaExhaustedError,
    get_default_rate_limiter,
)
from src.market_data.sahmk.operation_scope import INGESTION, operation_scope
from src.market_data.sahmk.request_priority import BACKGROUND, priority_scope
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock

logger = logging.getLogger(__name__)

# Independent of MarketIntelligenceScheduler's own
# "basirah:scheduler:market_intelligence:leader" lease -- the two
# schedulers' leaderships are tracked separately (a worker could
# legitimately lead one but not the other), each via its own
# SchedulerLeaderLock instance/key.
_INGESTION_LEASE_KEY = "basirah:ingestion_scheduler:leader"

# Added on top of the quota governor's own reset instant so a job
# deferred right at the boundary doesn't retry a few seconds early
# (clock skew between this process and whatever set resets_at_utc,
# plus giving the day-count rollover a moment to actually take effect)
# and immediately get deferred again.
_QUOTA_RETRY_SAFETY_BUFFER = timedelta(minutes=5)


def _find_quota_exceeded_cause(exc: BaseException, max_depth: int = 5) -> Optional[SahmkRateLimitExceededError]:
    """Walks an exception's __cause__/__context__ chain looking for a
    SahmkRateLimitExceededError (or a subclass -- SahmkQuotaReserved
    ForCriticalError, SahmkUpstreamQuotaExhaustedError). Needed because
    provider_factory/fundamental_provider_factory re-raise the rate
    limiter's own exception as StrictRealDataUnavailableError (a bare
    `raise NewError(...)` inside an `except ... as exc:` block, which
    Python sets __context__ for automatically even with no explicit
    `raise ... from exc`) -- see their own connectivity-probe except
    clauses. Bounded depth: this only ever needs to see through one or
    two wrapping layers; an unbounded walk would risk an infinite loop
    if something's __context__ ever pointed back at itself."""
    current: Optional[BaseException] = exc
    for _ in range(max_depth):
        if current is None:
            return None
        if isinstance(current, SahmkRateLimitExceededError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _compute_quota_retry_at(quota_exc: SahmkRateLimitExceededError) -> datetime:
    """SahmkUpstreamQuotaExhaustedError carries SAHMK's own real
    evidence-based reset instant (reset_at_utc) -- used verbatim when
    available, since it's more authoritative than this limiter's own
    UTC-midnight estimate. Every other SahmkRateLimitExceededError
    (plain daily exhaustion, or SahmkQuotaReservedForCriticalError --
    background dipping into the critical reserve) has no such
    attribute, so the rate limiter's own resets_at_utc (a real,
    zero-network-call read of its own tracked state, always the next
    UTC midnight) is the correct fallback -- background capacity does
    not free up mid-day; it only resets at day rollover."""
    if isinstance(quota_exc, SahmkUpstreamQuotaExhaustedError):
        reset_at = quota_exc.reset_at_utc
    else:
        status = get_default_rate_limiter().get_status()
        reset_at = datetime.fromisoformat(str(status["resets_at_utc"]))
    return reset_at + _QUOTA_RETRY_SAFETY_BUFFER


class _NonDisconnectingProviderProxy:
    """Wraps a provider obtained from provider_factory/
    fundamental_provider_factory's process-wide cache.

    Every ingest_*() function calls provider.authenticate() at the
    start and provider.disconnect() at the end of its own run -- their
    own established M2.1/M2.3 contract, unchanged here. That contract
    is correct for a caller that owns the provider for exactly one run,
    but the scheduler's provider is a *shared, cached* instance the
    provider_factory layer expects to keep serving other callers (the
    API layer, or the next scheduled run within the cache window).
    Disconnecting it out from under them would break those other
    callers. authenticate() is skipped for the same reason in reverse:
    provider_factory already authenticated this instance once, during
    selection, to decide it was worth caching at all.

    Every other call (including provider-specific "extra" methods not
    on IMarketDataProvider/IFundamentalDataProvider, like
    get_dividends()/get_symbol_directory()) passes straight through via
    __getattr__.
    """

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    async def authenticate(self) -> bool:
        return True

    async def disconnect(self) -> None:
        pass


async def run_ingestion_job(
    job_name: str,
    job_fn: Callable[[], Awaitable[IngestionResult]],
    session_factory: Callable[[], Session],
    max_attempts: Optional[int] = None,
    retry_base_delay_seconds: Optional[float] = None,
) -> IngestionRunLog:
    """Executes one job run to completion: writes a RUNNING
    IngestionRunLog row immediately, retries `job_fn` with exponential
    backoff if it raises, updates the same row in place with the
    outcome, and emits a structured log line. Never raises -- a job
    that fails every attempt is recorded as FAILED, not propagated,
    so one job's failure can't take down the scheduler's other loops
    or crash the process.
    """
    max_attempts = max_attempts if max_attempts is not None else ingestion_config.get_ingestion_job_max_attempts()
    retry_base_delay_seconds = (
        retry_base_delay_seconds
        if retry_base_delay_seconds is not None
        else ingestion_config.get_ingestion_job_retry_base_delay_seconds()
    )

    started_at = datetime.now(timezone.utc)
    session = session_factory()
    try:
        run_log = IngestionRunLog(job_name=job_name, started_at=started_at)
        session.add(run_log)
        session.commit()
        run_log_id = run_log.id
    finally:
        session.close()

    result: Optional[IngestionResult] = None
    error_summary: Optional[str] = None
    retry_count = 0
    deferred_until: Optional[datetime] = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = await job_fn()
            retry_count = attempt - 1  # set once, at the final (successful) outcome
            break
        except Exception as exc:  # noqa: BLE001 -- deliberate: any job failure must be caught and logged, never crash the scheduler loop
            quota_exc = _find_quota_exceeded_cause(exc)
            if quota_exc is not None:
                # Not a genuine ingestion failure: the quota governor
                # correctly refused this background request to protect
                # the reserve for live-market-critical operations.
                # Retrying within seconds (the exponential-backoff loop
                # below) cannot possibly help -- background capacity
                # only frees up at the next UTC day rollover -- so this
                # stops immediately rather than burning the remaining
                # attempts/backoff sleeps on a wall that won't move.
                retry_count = attempt - 1
                deferred_until = _compute_quota_retry_at(quota_exc)
                error_summary = f"Deferred (SAHMK quota protection): {quota_exc}"
                logger.info(
                    "Ingestion job '%s' deferred on attempt %d/%d -- SAHMK background quota "
                    "unavailable, will retry at %s: %s",
                    job_name,
                    attempt,
                    max_attempts,
                    deferred_until.isoformat(),
                    quota_exc,
                )
                break
            if attempt >= max_attempts:
                retry_count = attempt - 1  # set once, at the final (failed) outcome
                error_summary = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "Ingestion job '%s' failed after %d attempt(s): %s",
                    job_name,
                    attempt,
                    exc,
                    exc_info=True,
                )
                break
            delay = retry_base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Ingestion job '%s' attempt %d/%d failed (retrying in %.1fs): %s",
                job_name,
                attempt,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    finished_at = datetime.now(timezone.utc)
    duration_seconds = (finished_at - started_at).total_seconds()

    session = session_factory()
    try:
        run_log = session.query(IngestionRunLog).filter_by(id=run_log_id).one()
        run_log.finished_at = finished_at
        run_log.duration_seconds = round(duration_seconds, 3)
        run_log.retry_count = retry_count

        if result is not None:
            run_log.symbols_requested = result.symbols_requested
            run_log.symbols_succeeded = result.symbols_succeeded
            run_log.symbols_failed = result.symbols_failed
            run_log.rows_upserted = result.rows_upserted
            if result.symbols_failed == 0:
                run_log.status = IngestionJobStatus.SUCCESS
            elif result.symbols_succeeded > 0:
                run_log.status = IngestionJobStatus.PARTIAL
            else:
                run_log.status = IngestionJobStatus.FAILED
            if result.errors:
                summarized = "; ".join(f"{k}: {v}" for k, v in list(result.errors.items())[:10])
                run_log.error_summary = summarized
            if result.zero_progress:
                run_log.zero_progress_summary = "; ".join(
                    f"{k}: {v}" for k, v in list(result.zero_progress.items())[:10]
                )
        elif deferred_until is not None:
            run_log.status = IngestionJobStatus.DEFERRED
            run_log.error_summary = error_summary
            run_log.next_retry_at = deferred_until
        else:
            run_log.status = IngestionJobStatus.FAILED
            run_log.error_summary = error_summary

        session.commit()
        status = run_log.status
        logged_requested = run_log.symbols_requested
        logged_succeeded = run_log.symbols_succeeded
        logged_failed = run_log.symbols_failed
        logged_rows = run_log.rows_upserted
    finally:
        session.close()

    logger.info(
        "Ingestion job '%s' finished: status=%s duration=%.2fs requested=%d succeeded=%d "
        "failed=%d rows_upserted=%d retries=%d",
        job_name,
        status.value,
        duration_seconds,
        logged_requested,
        logged_succeeded,
        logged_failed,
        logged_rows,
        retry_count,
    )
    return run_log


def reap_stale_ingestion_runs(session: Session, max_age_hours: float) -> List[IngestionRunLog]:
    """Mirrors MarketIntelligenceRepository.reap_stale_runs for the same
    failure mode: a process killed/restarted between run_ingestion_job's
    RUNNING insert and its finished_at update leaves a row RUNNING
    forever, indistinguishable from a genuinely in-progress job --
    without this, POST /full-discovery's in-flight guard (matches on
    finished_at IS NULL) would block every future trigger permanently.
    Marks any such row older than max_age_hours as FAILED so a new
    discovery pass can proceed. Returns the runs it reaped, for logging.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    candidates = (
        session.query(IngestionRunLog).filter(IngestionRunLog.finished_at.is_(None)).all()
    )
    reaped = []
    for run in candidates:
        started_at = run.started_at
        if started_at.tzinfo is None:
            # Same SQLite naive-datetime pitfall documented in
            # MarketIntelligenceRepository.reap_stale_runs -- started_at
            # is always written as UTC, so a naive value read back is
            # treated as UTC rather than compared against an aware "now."
            started_at = started_at.replace(tzinfo=timezone.utc)
        if started_at < cutoff:
            run.finished_at = datetime.now(timezone.utc)
            run.status = IngestionJobStatus.FAILED
            run.error_summary = (
                f"Reaped: still RUNNING {max_age_hours:.1f}h+ after starting -- "
                "treated as crashed/restarted, never reached run_ingestion_job's own finish step."
            )
            reaped.append(run)
    if reaped:
        session.commit()
    return reaped


class IngestionScheduler:
    """Owns one recurring asyncio.Task per ingestion job. See module
    docstring for the overall design."""

    def __init__(
        self,
        session_factory: Optional[Callable[[], Session]] = None,
        market_provider_getter: Optional[Callable[[], Awaitable[object]]] = None,
        fundamental_provider_getter: Optional[Callable[[], Awaitable[object]]] = None,
        leader_lock: Optional[SchedulerLeaderLock] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._get_market_provider = market_provider_getter or get_market_data_provider
        self._get_fundamental_provider = fundamental_provider_getter or get_fundamental_data_provider
        self._leader_lock = leader_lock or SchedulerLeaderLock(lease_key=_INGESTION_LEASE_KEY)
        self._tasks: List[asyncio.Task] = []
        self._leadership_task: Optional[asyncio.Task] = None
        self._is_leader: bool = False
        self._skipped_due_to_not_leader_count: int = 0

    @staticmethod
    def _default_session_factory() -> Session:
        return database.get_session_factory()()

    @property
    def is_running(self) -> bool:
        return len(self._tasks) > 0

    @property
    def is_leader(self) -> bool:
        """Whether THIS process currently holds the ingestion-scheduler
        lease -- real, current state, not cached across a long window
        (the heartbeat task renews/re-checks it every
        `get_ingestion_leader_heartbeat_seconds()`). A caller polling
        this across multiple requests to a multi-worker deployment will
        see it True on whichever single worker happens to serve that
        request only if that worker is the leader -- exactly the signal
        needed to prove "only one worker leads" from outside the
        process."""
        return self._is_leader

    @property
    def skipped_due_to_not_leader_count(self) -> int:
        """How many job ticks this process has skipped (zero SAHMK
        cost, no IngestionRunLog row written) because it was not the
        leader at that tick -- observability only, never used for any
        scheduling decision."""
        return self._skipped_due_to_not_leader_count

    async def run_all_jobs_once(self) -> List[IngestionRunLog]:
        """Runs the same four jobs `start()`'s recurring loops would
        eventually run, once, in dependency order -- symbols first (so
        a freshly discovered symbol's Stock row exists before the
        other three jobs resolve their target list via
        `_resolve_target_symbols()`), then historical_ohlcv,
        fundamentals, dividends. Used by the staff-only manual
        full-discovery admin route so an operator can grow the
        universe on demand without needing the always-on recurring
        scheduler (INGESTION_SCHEDULER_ENABLED) turned on. Reuses
        `run_ingestion_job` and the same private per-job wiring
        `start()`'s loops use -- no parallel implementation."""
        run_logs: List[IngestionRunLog] = []
        for job_name, job_fn in (
            ("symbols", self._run_symbols),
            ("historical_ohlcv", self._run_historical_ohlcv),
            ("fundamentals", self._run_fundamentals),
            ("dividends", self._run_dividends),
        ):
            run_logs.append(await run_ingestion_job(job_name, job_fn, self._session_factory))
        return run_logs

    def start(self) -> None:
        if self._tasks:
            logger.warning("IngestionScheduler.start() called while already running -- ignoring.")
            return

        self._reap_stale_runs_once()

        # Synchronous first attempt so `is_leader` reflects real state
        # the instant start() returns, rather than depending on
        # asyncio's task-scheduling order to run the heartbeat task's
        # first iteration before any job loop's first tick.
        self._is_leader = self._leader_lock.try_acquire_or_renew(
            ingestion_config.get_ingestion_leader_lease_seconds()
        )
        self._leadership_task = asyncio.ensure_future(self._leadership_heartbeat_loop())

        job_specs = [
            ("symbols", ingestion_config.get_symbols_sync_interval_seconds, self._run_symbols),
            (
                "historical_ohlcv",
                ingestion_config.get_ohlcv_sync_next_delay_seconds,
                self._run_historical_ohlcv,
            ),
            (
                "fundamentals",
                ingestion_config.get_fundamentals_sync_interval_seconds,
                self._run_fundamentals,
            ),
            ("dividends", ingestion_config.get_dividends_sync_interval_seconds, self._run_dividends),
        ]
        for job_name, interval_fn, job_fn in job_specs:
            initial_delay = self._compute_initial_delay(job_name)
            task = asyncio.ensure_future(self._loop(job_name, interval_fn, job_fn, initial_delay))
            self._tasks.append(task)

        logger.info(
            "IngestionScheduler started %d job loop(s) (is_leader=%s): %s",
            len(self._tasks), self._is_leader, [s[0] for s in job_specs],
        )

    async def stop(self) -> None:
        # Cancel every task -- leadership heartbeat AND all job loops --
        # before awaiting any of them. Awaiting one task hands control
        # back to the event loop, which would otherwise get a chance to
        # run any not-yet-cancelled task's *first* real step; cancelling
        # everything up front guarantees every task is already marked
        # cancelled by the time any of them actually runs.
        if self._leadership_task is not None:
            self._leadership_task.cancel()
        for task in self._tasks:
            task.cancel()
        if self._leadership_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._leadership_task
            self._leadership_task = None
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._leader_lock.release()
        self._is_leader = False
        logger.info("IngestionScheduler stopped.")

    async def _leadership_heartbeat_loop(self) -> None:
        """Renews (or re-attempts) this worker's ingestion-scheduler
        lease on a short, fixed cadence -- deliberately independent of
        any single job's own (often much longer) interval, so
        leadership itself fails over to another worker within roughly
        one heartbeat interval of the previous leader's process dying,
        even though that new leader's first actual job run still waits
        for that job's own normal schedule (see `_loop`)."""
        heartbeat_seconds = ingestion_config.get_ingestion_leader_heartbeat_seconds()
        lease_seconds = ingestion_config.get_ingestion_leader_lease_seconds()
        while True:
            await asyncio.sleep(heartbeat_seconds)
            try:
                self._is_leader = self._leader_lock.try_acquire_or_renew(lease_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- a heartbeat failure must never crash the process; fail closed instead
                logger.exception("IngestionScheduler: unexpected error during leadership heartbeat.")
                self._is_leader = False

    def _compute_initial_delay(self, job_name: str) -> float:
        """Persisted-retry-state on restart: if this job's most recent
        run was DEFERRED (SAHMK background quota unavailable) with a
        next_retry_at still in the future, a freshly (re)started
        scheduler must honor that instead of running the job
        immediately -- which would just hit the same quota wall again
        and log a redundant deferral. Returns 0.0 (run immediately, the
        existing on-enable behavior) for every other case: no prior
        run, a prior run that already succeeded/failed/partial'd, or a
        DEFERRED run whose retry time has already passed."""
        session = self._session_factory()
        try:
            latest = (
                session.query(IngestionRunLog)
                .filter(IngestionRunLog.job_name == job_name)
                .order_by(IngestionRunLog.id.desc())
                .first()
            )
        finally:
            session.close()
        if latest is None or latest.status is not IngestionJobStatus.DEFERRED or latest.next_retry_at is None:
            return 0.0
        next_retry_at = latest.next_retry_at
        if next_retry_at.tzinfo is None:
            next_retry_at = next_retry_at.replace(tzinfo=timezone.utc)
        delay = (next_retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delay)

    def _reap_stale_runs_once(self) -> None:
        """Mirrors MarketIntelligenceScheduler's own stale-lock reap: a
        process kill between an IngestionRunLog's RUNNING insert and its
        finish never reaches run_ingestion_job's own finish step,
        leaving that row RUNNING forever -- indistinguishable from a
        genuinely in-progress job to POST /full-discovery's in-flight
        guard, which would then block every future discovery pass
        (scheduled or manual) permanently after a crash. Reaped once
        here, right before this scheduler starts its recurring loops."""
        session = self._session_factory()
        try:
            reaped = reap_stale_ingestion_runs(session, ingestion_config.get_max_ingestion_job_run_duration_hours())
            if reaped:
                logger.warning(
                    "IngestionScheduler.start(): reaped %d stale IngestionRunLog row(s) "
                    "(run id(s): %s) before scheduling.",
                    len(reaped),
                    [r.id for r in reaped],
                )
        finally:
            session.close()

    async def _loop(
        self,
        job_name: str,
        interval_fn: Callable[[], float],
        job_fn: Callable[[], Awaitable[IngestionResult]],
        initial_delay_seconds: float = 0.0,
    ) -> None:
        if initial_delay_seconds > 0:
            logger.info(
                "Ingestion job '%s' resuming a persisted quota-deferred wait -- "
                "sleeping %.0fs before its first run this process.",
                job_name,
                initial_delay_seconds,
            )
            await asyncio.sleep(initial_delay_seconds)
        while True:
            next_sleep_seconds = interval_fn()
            try:
                if not self._is_leader:
                    # Another worker holds the ingestion-scheduler
                    # lease -- this tick is skipped entirely: zero SAHMK
                    # cost, no IngestionRunLog row written. See the
                    # module docstring for the 2026-08-17 incident this
                    # closes (multi-worker duplicate ingestion).
                    self._skipped_due_to_not_leader_count += 1
                    logger.debug(
                        "Ingestion job '%s' skipped this tick -- this worker is not the "
                        "ingestion-scheduler leader.",
                        job_name,
                    )
                else:
                    run_log = await run_ingestion_job(job_name, job_fn, self._session_factory)
                    if run_log.status is IngestionJobStatus.DEFERRED and run_log.next_retry_at is not None:
                        # Quota-deferred: retry when the quota governor says
                        # background capacity will be available again, not
                        # on this job's normal (possibly much longer, e.g.
                        # daily/weekly) recurring interval -- otherwise a
                        # symbols/fundamentals job deferred once could stay
                        # stale for a full extra day/week even after the
                        # quota reset.
                        next_retry_at = run_log.next_retry_at
                        if next_retry_at.tzinfo is None:
                            next_retry_at = next_retry_at.replace(tzinfo=timezone.utc)
                        next_sleep_seconds = max(
                            0.0, (next_retry_at - datetime.now(timezone.utc)).total_seconds()
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                # run_ingestion_job itself already catches and records job_fn
                # failures -- reaching here means writing the run log failed,
                # a DB-layer problem, not an ingestion one. Logged, not raised,
                # so this one job's loop keeps running on schedule.
                logger.exception(
                    "Unexpected error recording ingestion job '%s' (outside its own "
                    "retry handling).",
                    job_name,
                )
            await asyncio.sleep(next_sleep_seconds)

    def _resolve_target_symbols(self) -> List[str]:
        """The symbol set every job except `_run_symbols` operates on:
        the explicitly configured seed list, unioned with every symbol
        the `symbols` job has already discovered and left active in the
        `Stock` table (real Tadawul/Nomu equities when
        INGESTION_AUTO_DISCOVER_SYMBOLS=true and universe_policy has
        excluded non-equity instruments -- see ingest_symbols.py).

        Without this union, OHLCV/fundamentals/dividends would silently
        stay capped at INGESTION_SYMBOL_UNIVERSE (5 symbols by default)
        forever, even after the symbols job discovers the full market --
        SymbolSelector requires PriceBar rows to select a symbol for
        scanning, so those symbols would exist as inert Stock rows but
        never actually be scanned, ranked, or recommended. This was the
        confirmed root cause of production only ever surfacing a small,
        fixed handful of stocks. Falls back to exactly the configured
        seed list when the DB has no other active Stock rows yet (cold
        start, or auto-discovery disabled) -- behavior-preserving in
        that case."""
        configured = ingestion_config.get_ingestion_symbol_universe()
        session = self._session_factory()
        try:
            discovered = [
                row[0]
                for row in session.query(Stock.symbol).filter(Stock.is_active.is_(True)).all()
            ]
        finally:
            session.close()
        return list(dict.fromkeys(list(configured) + discovered))

    def _resolve_ohlcv_target_symbols(self) -> List[str]:
        """`_resolve_target_symbols()`, further unioned with every
        symbol that has a still-`PENDING` `DecisionV2Outcome` -- the
        OHLCV persistence / outcome-tracking fix (2026-08-23, see
        `src.market_data.ingestion.outcome_tracking`'s module docstring
        for the full root-cause writeup). A symbol must not stop
        receiving OHLCV updates merely because it is no longer selected
        by the next Stage 2 scan or because its general `Stock.
        is_active` flag changes for an unrelated reason (a directory
        reclassification, a temporary provider gap) -- an outstanding
        signal's own evaluation need is a first-class, independent
        reason to keep fetching. Deliberately scoped to OHLCV only
        (fundamentals/dividends still use the unmodified `_resolve_
        target_symbols()`): those two data types are not what
        `evaluate_pending_outcomes()` reads, so extending their target
        list would add SAHMK cost with no outcome-tracking benefit."""
        base = self._resolve_target_symbols()
        session = self._session_factory()
        try:
            pending = pending_signal_symbols(session)
        finally:
            session.close()
        return list(dict.fromkeys(base + pending))

    async def _run_symbols(self) -> IngestionResult:
        with priority_scope(BACKGROUND), operation_scope(INGESTION):
            provider = _NonDisconnectingProviderProxy(await self._get_market_provider())
            symbols = ingestion_config.get_ingestion_symbol_universe()
            return await sync_symbols(
                symbols,
                provider,
                self._session_factory,
                discover_all=ingestion_config.is_symbol_auto_discovery_enabled(),
            )

    async def _run_historical_ohlcv(self) -> IngestionResult:
        with priority_scope(BACKGROUND), operation_scope(INGESTION):
            provider = _NonDisconnectingProviderProxy(await self._get_market_provider())
            symbols = self._resolve_ohlcv_target_symbols()
            return await ingest_historical_ohlcv(
                symbols,
                provider,
                self._session_factory,
                backfill_days=ingestion_config.get_ohlcv_backfill_days(),
            )

    async def _run_fundamentals(self) -> IngestionResult:
        with priority_scope(BACKGROUND), operation_scope(INGESTION):
            provider = _NonDisconnectingProviderProxy(await self._get_fundamental_provider())
            symbols = self._resolve_target_symbols()
            return await ingest_fundamentals(
                symbols,
                provider,
                self._session_factory,
                period_type=ingestion_config.get_fundamentals_period_type(),
            )

    async def _run_dividends(self) -> IngestionResult:
        with priority_scope(BACKGROUND), operation_scope(INGESTION):
            provider = _NonDisconnectingProviderProxy(await self._get_fundamental_provider())
            symbols = self._resolve_target_symbols()
            return await ingest_dividends(symbols, provider, self._session_factory)
