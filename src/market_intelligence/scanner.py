"""MarketScanner: runs the reused analysis pipeline (build_analysis_
context -> AnalystEngine.analyze -- which itself already calls
AIDecisionEngine -> RecommendationEngine -> TechnicalAnalysisEngine/
FundamentalAnalysisEngine, unmodified) against many symbols.

Never duplicates provider logic: the same `IMarketDataProvider`
instance the REST layer already gets from
`src.api.dependencies.get_market_provider` is passed in and reused for
every symbol, exactly as `/decision`/`/analyst-report` already use it
for one symbol at a time.

Concurrency is bounded by an `asyncio.Semaphore` sized from
`MARKET_SCAN_BATCH_SIZE` (default 1, i.e. sequential) -- the
architecture is already "future parallel execution"-ready (each
concurrent task opens its own DB session via `session_factory()`, so
raising the batch size is safe once a deployment's DB pool is sized
for it) without this milestone needing to prove concurrent scanning at
scale.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.analysis.analyst.analyst_engine import AnalystEngine
from src.analysis.context_builder import build_analysis_context
from src.domain.models import PeriodType, Stock
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_intelligence.config import (
    get_scan_batch_size,
    get_scan_max_attempts,
    get_scan_retry_base_delay_seconds,
)
from src.market_intelligence.types import MarketScanSummary, SymbolScanOutcome

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        market_provider: IMarketDataProvider,
        analyst_engine: Optional[AnalystEngine] = None,
        period_type: PeriodType = PeriodType.ANNUAL,
    ):
        self._session_factory = session_factory
        self._market_provider = market_provider
        self._analyst_engine = analyst_engine or AnalystEngine()
        self._period_type = period_type

    async def scan(self, symbols: List[str]) -> List[SymbolScanOutcome]:
        semaphore = asyncio.Semaphore(max(1, get_scan_batch_size()))
        tasks = [self._scan_one_bounded(symbol, semaphore) for symbol in symbols]
        return list(await asyncio.gather(*tasks))

    @staticmethod
    def summarize(outcomes: List[SymbolScanOutcome], started_at: datetime, finished_at: Optional[datetime] = None) -> MarketScanSummary:
        finished_at = finished_at or datetime.now(timezone.utc)
        succeeded = sum(1 for o in outcomes if o.success)
        failed = sum(1 for o in outcomes if not o.success and o.error is not None)
        skipped = len(outcomes) - succeeded - failed
        return MarketScanSummary(
            total_requested=len(outcomes),
            total_succeeded=succeeded,
            total_skipped=skipped,
            total_failed=failed,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
        )

    async def _scan_one_bounded(self, symbol: str, semaphore: asyncio.Semaphore) -> SymbolScanOutcome:
        async with semaphore:
            return await self._scan_one_with_retry(symbol)

    async def _scan_one_with_retry(self, symbol: str) -> SymbolScanOutcome:
        """Retries only real, unexpected failures -- a symbol correctly
        identified as having insufficient data is not an error and is
        never retried (retrying would only waste time; more attempts
        do not manufacture missing data)."""
        max_attempts = get_scan_max_attempts()
        retry_base_delay = get_scan_retry_base_delay_seconds()
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await self._scan_one(symbol)
            except Exception as exc:  # noqa: BLE001 -- deliberate: one symbol's failure must never abort the whole scan.
                last_error = exc
                if attempt >= max_attempts:
                    break
                delay = retry_base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Market scan for '%s' attempt %d/%d failed (retrying in %.1fs): %s",
                    symbol, attempt, max_attempts, delay, exc,
                )
                await asyncio.sleep(delay)

        logger.error("Market scan for '%s' failed after %d attempt(s): %s", symbol, max_attempts, last_error, exc_info=True)
        return SymbolScanOutcome(symbol=symbol, sector=None, success=False, report=None, error=str(last_error))

    async def _scan_one(self, symbol: str) -> SymbolScanOutcome:
        session = self._session_factory()
        try:
            stock = session.query(Stock).filter(Stock.symbol == symbol).one_or_none()
            if stock is None:
                return SymbolScanOutcome(
                    symbol=symbol, sector=None, success=False, report=None, skipped_reason="stock_not_registered"
                )

            context = await build_analysis_context(stock, self._period_type, session, self._market_provider)
            if context.technical_result is None and context.fundamental_result is None:
                return SymbolScanOutcome(
                    symbol=symbol, sector=stock.sector, success=False, report=None, skipped_reason="insufficient_data"
                )

            report = await self._analyst_engine.analyze(context)

            return SymbolScanOutcome(
                symbol=symbol,
                sector=stock.sector,
                success=True,
                report=report,
                latest_price=context.latest_price,
                technical_snapshot=context.technical_result.latest_snapshot() if context.technical_result else None,
                fundamental_snapshot=context.fundamental_result.latest_snapshot() if context.fundamental_result else None,
                context=context,
            )
        finally:
            session.close()
