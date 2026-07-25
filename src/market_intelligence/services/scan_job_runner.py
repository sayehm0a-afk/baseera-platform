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

from src.domain.models import MarketScanStatus
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_intelligence.market_engine import MarketIntelligenceEngine
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository

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
    engine = MarketIntelligenceEngine(session_factory, market_provider, repository=repository)
    started_at = datetime.now(timezone.utc)

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            await engine.execute_scan(run_id, symbols)
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
