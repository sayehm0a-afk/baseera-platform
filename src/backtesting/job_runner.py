"""Runs one BacktestRun to completion in the background -- the same
shape src.market_data.ingestion.scheduler.run_ingestion_job already
established (write a RUNNING row immediately, retry the whole
operation with exponential backoff only on a transient infrastructure
failure, update the same row in place with the final outcome, never
let an exception escape), applied to backtests instead of ingestion
jobs.

`BacktestingEngine.run()` is fully synchronous (a blocking, sync-
SQLAlchemy-Session-based loop, potentially long-running for a large
symbol universe/date range) -- run via `asyncio.to_thread` so it never
blocks the event loop FastAPI's other requests depend on, which is
what makes "do not let a synchronous HTTP request block for a large
full-market backtest" (Phase 7) actually true: `POST /api/v1/backtests`
only ever creates the row and schedules this coroutine, it never awaits
it to completion.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.backtesting.calibration.parameters import build_strategy_kwargs
from src.backtesting.engine import BacktestConfig, BacktestingEngine
from src.domain.models import BacktestRun, BacktestRunStatus, CalibrationConfig

logger = logging.getLogger(__name__)

# Only these are worth retrying the whole run for -- a DB connectivity
# blip, not a bad configuration (ValueError from an unknown strategy
# name, a malformed calibration config) or a programming bug, neither
# of which retrying would ever fix. Same "never let a business error
# masquerade as an infrastructure failure" discipline SahmkClient's
# circuit breaker already applies, ported to this job's own retry gate.
_TRANSIENT_EXCEPTIONS = (OperationalError, ConnectionError, TimeoutError, OSError)

_PROGRESS_COMMIT_EVERY = 5  # throttle DB writes -- not one commit per evaluation


class _ProgressReporter:
    """Bundles the progress_callback/is_cancelled pair BacktestingEngine.run()
    calls, throttling how often either actually touches the database.
    Committing on every check (not just every Nth) is what lets
    `is_cancelled()` see a `cancel_requested=True` written by a
    different request's session -- SQLite/Postgres alike only make a
    concurrent commit visible to a session that starts a fresh
    transaction, which `session.commit()` does here as a side effect.
    """

    def __init__(self, session: Session, run_id: int):
        self._session = session
        self._run_id = run_id
        self._checks = 0
        self.cancelled = False

    def progress_callback(self, done: int, total: int) -> None:
        self._checks += 1
        if done < total and self._checks % _PROGRESS_COMMIT_EVERY != 0:
            return
        self._session.query(BacktestRun).filter_by(id=self._run_id).update(
            {"progress_current": done, "progress_total": total}
        )
        self._session.commit()

    def is_cancelled(self) -> bool:
        if self.cancelled:
            return True
        flag = (
            self._session.query(BacktestRun.cancel_requested).filter_by(id=self._run_id).scalar()
        )
        self.cancelled = bool(flag)
        return self.cancelled


def _build_config(run: BacktestRun, session: Session) -> BacktestConfig:
    strategy_kwargs = None
    if run.calibration_version:
        calibration = session.query(CalibrationConfig).filter_by(version=run.calibration_version).one_or_none()
        if calibration is None:
            raise ValueError(f"BacktestRun {run.id} references unknown calibration_version {run.calibration_version!r}")
        strategy_kwargs = build_strategy_kwargs(calibration.config, name=f"calibrated-{calibration.version}")

    return BacktestConfig(
        symbols=list(run.symbols),
        start_date=run.start_date,
        end_date=run.end_date,
        data_provenance_mode=run.data_provenance_mode,
        strategy=run.strategy,
        strategy_kwargs=strategy_kwargs,
        evaluation_frequency_days=run.evaluation_frequency_days,
        holding_horizon_days=run.holding_horizon_days,
        target_price_horizon_days=run.target_price_horizon_days,
        transaction_cost_bps=float(run.transaction_cost_bps),
        slippage_bps=float(run.slippage_bps),
        confidence_threshold=float(run.confidence_threshold) if run.confidence_threshold is not None else None,
        recommendation_threshold=run.recommendation_threshold,
        fundamental_reporting_lag_days=run.fundamental_reporting_lag_days,
        calibration_version=run.calibration_version,
    )


def _execute_sync(session: Session, run_id: int) -> dict:
    """The actual blocking work -- runs inside asyncio.to_thread."""
    run = session.query(BacktestRun).filter_by(id=run_id).one()
    config = _build_config(run, session)
    reporter = _ProgressReporter(session, run_id)
    report = BacktestingEngine().run(
        session, config, run_id=run_id,
        progress_callback=reporter.progress_callback, is_cancelled=reporter.is_cancelled,
    )
    report["_cancelled_by_request"] = reporter.cancelled
    return report


async def run_backtest_job(
    run_id: int,
    session_factory: Callable[[], Session],
    max_attempts: int = 2,
    retry_base_delay_seconds: float = 5.0,
) -> None:
    """Executes BacktestRun `run_id` to completion. Never raises --
    scheduled via `asyncio.ensure_future` (fire-and-forget) from the
    REST layer, so an exception escaping this function would surface
    nowhere except an "exception was never retrieved" warning and
    leave the run stuck in whatever state it was last in. Every stage,
    including the very first "mark as RUNNING" write, is inside the
    top-level guard below -- even a failure before any real work
    starts (e.g. the database itself is unreachable) is logged, never
    propagated.
    """
    started_at = datetime.now(timezone.utc)
    try:
        await _run_and_record(run_id, session_factory, started_at, max_attempts, retry_base_delay_seconds)
    except Exception:  # noqa: BLE001 -- deliberate: this coroutine must never raise, full stop; see docstring.
        logger.error("Backtest run %d: unhandled failure outside the normal retry/record path.", run_id, exc_info=True)


async def _run_and_record(
    run_id: int,
    session_factory: Callable[[], Session],
    started_at: datetime,
    max_attempts: int,
    retry_base_delay_seconds: float,
) -> None:
    session = session_factory()
    try:
        session.query(BacktestRun).filter_by(id=run_id).update(
            {"status": BacktestRunStatus.RUNNING, "started_at": started_at}
        )
        session.commit()
    finally:
        session.close()

    report: Optional[dict] = None
    error_message: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        session = session_factory()
        try:
            report = await asyncio.to_thread(_execute_sync, session, run_id)
            break
        except _TRANSIENT_EXCEPTIONS as exc:
            if attempt >= max_attempts:
                error_message = f"{type(exc).__name__}: {exc}"
                logger.error("Backtest run %d failed after %d attempt(s): %s", run_id, attempt, exc, exc_info=True)
                break
            delay = retry_base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Backtest run %d attempt %d/%d failed (retrying in %.1fs): %s", run_id, attempt, max_attempts, delay, exc
            )
            await asyncio.sleep(delay)
        except Exception as exc:  # noqa: BLE001 -- deliberate: a non-transient failure (bad config, programming
            # error) must still be recorded, not silently crash the job -- it is just never retried.
            error_message = f"{type(exc).__name__}: {exc}"
            logger.error("Backtest run %d failed (non-transient): %s", run_id, exc, exc_info=True)
            break
        finally:
            session.close()

    finished_at = datetime.now(timezone.utc)
    duration_seconds = (finished_at - started_at).total_seconds()

    session = session_factory()
    try:
        run = session.query(BacktestRun).filter_by(id=run_id).one()
        run.finished_at = finished_at
        run.duration_seconds = round(duration_seconds, 3)

        if report is not None:
            cancelled = report.pop("_cancelled_by_request", False)
            run.metrics = report
            run.status = BacktestRunStatus.CANCELLED if cancelled else BacktestRunStatus.SUCCESS
            run.progress_current = report.get("evaluated_count", run.progress_current)
        else:
            run.status = BacktestRunStatus.FAILED
            run.error_message = error_message

        session.commit()
        status = run.status
    finally:
        session.close()

    logger.info("Backtest run %d finished: status=%s duration=%.2fs", run_id, status.value, duration_seconds)
