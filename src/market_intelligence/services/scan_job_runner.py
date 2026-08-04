"""Runs one MarketScanRun to completion in the background -- the same
shape src.backtesting.job_runner.run_backtest_job and
src.market_data.ingestion.scheduler.run_ingestion_job already
established (write/track a RUNNING row, retry only a transient
infrastructure failure, record the final outcome, never let an
exception escape), applied to market scans instead of backtests/
ingestion jobs.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.domain.models import MarketScanStatus, Stock
from src.market_data import config as market_data_config
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_intelligence.market_engine import MarketIntelligenceEngine
from src.market_intelligence.preflight import run_sahmk_preflight
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scan_progress import ScanProgressTracker
from src.market_intelligence.symbol_selector import SymbolSelector

logger = logging.getLogger(__name__)

# Same reasoning as backtesting/job_runner.py's own _TRANSIENT_EXCEPTIONS:
# only worth retrying the whole scan for a DB connectivity blip, never for
# a programming bug or a business-logic failure that retrying can't fix.
_TRANSIENT_EXCEPTIONS = (OperationalError, ConnectionError, TimeoutError, OSError)


async def run_market_scan_job(
    run_id: int,
    session_factory: Callable[[], Session],
    market_provider: IMarketDataProvider,
    symbols: Optional[List[str]] = None,
    max_attempts: int = 2,
    retry_base_delay_seconds: float = 5.0,
) -> None:
    """Never raises -- scheduled as a FastAPI BackgroundTask (or from
    MarketIntelligenceScheduler's own loop), so an exception escaping
    this function would surface nowhere except an "exception was never
    retrieved" warning and leave the run stuck RUNNING/PENDING forever.
    """
    repository = MarketIntelligenceRepository()
    started_at = datetime.now(timezone.utc)

    # Strict real-data mode's hard pre-scan gate (Basirah production
    # readiness mandate): a full-market scan may not even begin unless
    # a real, authenticated SAHMK request has just succeeded. Checked
    # first, before any progress tracking or scan work starts, so a
    # blocked run fails immediately and visibly rather than silently
    # falling back to whatever provider it was handed.
    if market_data_config.is_strict_real_data_enabled():
        preflight = await run_sahmk_preflight(session_factory)
        if not preflight.ready:
            logger.error(
                "Market scan run %d blocked by strict real-data pre-flight: %s",
                run_id, preflight.reason,
            )
            session = session_factory()
            try:
                repository.finish_run(
                    session, run_id, MarketScanStatus.FAILED,
                    symbols_succeeded=0, symbols_skipped=0, symbols_failed=0,
                    started_at=started_at,
                    error_summary=f"STRICT_REAL_DATA preflight failed: {preflight.reason}",
                )
            finally:
                session.close()
            return

    engine = MarketIntelligenceEngine(session_factory, market_provider, repository=repository)

    # Live progress (Basirah publishing its own progress, same reasoning
    # as the CI validation script's own tracker in
    # scripts/verify_sahmk_market_intelligence.py): resolves the same
    # symbol set execute_scan() is about to use, purely to know
    # eligible_discovered up front -- a read-only duplicate of
    # SymbolSelector's own query, not a second source of truth for
    # which symbols get scanned. output_dir=None: no GitHub Actions
    # step/filesystem here, this path is the REST-triggered scan, so
    # only the MarketScanProgress DB row is updated (read via
    # GET /api/v1/market/scan/{run_id}/progress).
    progress_tracker: Optional[ScanProgressTracker] = None
    resolve_session = session_factory()
    try:
        resolved_symbols = SymbolSelector().select(resolve_session, symbols)
        symbol_names = {
            row.symbol: {"name_en": row.name_en, "name_ar": row.name_ar}
            for row in resolve_session.query(Stock.symbol, Stock.name_en, Stock.name_ar)
            .filter(Stock.symbol.in_(resolved_symbols)).all()
        }
        progress_tracker = ScanProgressTracker(
            session_factory, run_id, eligible_discovered=len(resolved_symbols),
            output_dir=None, symbol_names=symbol_names, mode="rest_api_scan",
        )
    except Exception:  # noqa: BLE001 -- progress tracking must never block the real scan from starting
        logger.exception("Market scan run %d: failed to initialize live progress tracking", run_id)
    finally:
        resolve_session.close()

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            callbacks = {}
            if progress_tracker is not None:
                callbacks = dict(
                    on_symbol_start=progress_tracker.on_symbol_start,
                    on_symbol_complete=progress_tracker.on_symbol_complete,
                    on_retry=progress_tracker.on_retry,
                )
            await engine.execute_scan(run_id, symbols, **callbacks)
            if progress_tracker is not None:
                progress_tracker.finalize("COMPLETED")
            return
        except _TRANSIENT_EXCEPTIONS as exc:
            last_error = exc
            if attempt >= max_attempts:
                logger.error("Market scan run %d failed after %d attempt(s): %s", run_id, attempt, exc, exc_info=True)
                break
            delay = retry_base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Market scan run %d attempt %d/%d failed (retrying in %.1fs): %s",
                run_id, attempt, max_attempts, delay, exc,
            )
            await asyncio.sleep(delay)
        except Exception as exc:  # noqa: BLE001 -- deliberate: a non-transient failure must still be recorded, never crash the caller.
            last_error = exc
            logger.error("Market scan run %d failed (non-transient): %s", run_id, exc, exc_info=True)
            break

    if progress_tracker is not None:
        progress_tracker.finalize("FAILED")

    session = session_factory()
    try:
        repository.finish_run(
            session, run_id, MarketScanStatus.FAILED,
            symbols_succeeded=0, symbols_skipped=0, symbols_failed=0,
            started_at=started_at,
            error_summary=f"{type(last_error).__name__}: {last_error}" if last_error is not None else "unknown error",
        )
    finally:
        session.close()
