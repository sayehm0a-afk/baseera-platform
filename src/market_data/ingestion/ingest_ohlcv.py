"""OHLCV ingestion: pulls stock data from an IMarketDataProvider and
upserts it into the Stock/PriceBar tables.

Callable directly (not yet wired into RealWorker/RealTaskQueue --
that integration is out of M2.1's scope per the approved M2 blueprint,
which lists only this module's creation, not runtime-kernel wiring).
Its (task-dict-shaped) signature is deliberately compatible with
RealWorker.register_handler(task_type, handler) so a later milestone
can register it as a task handler without a redesign.

Fetches only the single latest bar per symbol (via get_stock_data());
for incremental/backfilling ingestion of a date range, see
ingest_historical_ohlcv.py, added alongside the ingestion scheduler --
this module's own contract (and every test against it) is unchanged.
"""

import logging
from typing import Callable, List

from sqlalchemy.orm import Session

from src.market_data.ingestion._common import IngestionResult, get_or_create_stock, upsert_price_bar
from src.market_data.providers.market_data_provider import IMarketDataProvider

logger = logging.getLogger(__name__)


async def ingest_ohlcv(
    symbols: List[str],
    provider: IMarketDataProvider,
    session_factory: Callable[[], Session],
) -> IngestionResult:
    """Fetch and upsert one day's OHLCV bar for each symbol.

    Each symbol is committed independently -- one symbol's failure
    (provider error, bad data) does not roll back or block the others.
    """
    result = IngestionResult(symbols_requested=len(symbols))

    await provider.authenticate()

    for symbol in symbols:
        session = session_factory()
        try:
            data = await provider.get_stock_data(symbol)
            stock = get_or_create_stock(session, symbol)
            upsert_price_bar(session, stock, data)
            session.commit()
            result.symbols_succeeded += 1
            result.rows_upserted += 1
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error("Failed to ingest OHLCV for symbol '%s': %s", symbol, exc)
        finally:
            session.close()

    await provider.disconnect()
    return result
