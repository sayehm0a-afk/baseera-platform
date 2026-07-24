"""Historical OHLCV backfill: pulls a date-range of bars from an
IMarketDataProvider's get_historical_ohlcv() and upserts every bar
into the Stock/PriceBar tables.

Deliberately reuses ingest_ohlcv.py's _get_or_create_stock and
_upsert_price_bar helpers instead of duplicating or modifying that
module -- both functions already do exactly what a range of bars also
needs (one bar dict in, one PriceBar row upserted), so importing them
keeps the single-day and historical-range ingestion paths from
silently diverging in behavior.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List

from sqlalchemy.orm import Session

from src.market_data.ingestion.ingest_ohlcv import _get_or_create_stock, _upsert_price_bar
from src.market_data.providers.market_data_provider import IMarketDataProvider

logger = logging.getLogger(__name__)


@dataclass
class HistoricalIngestionResult:
    """Summary of one ingest_historical_ohlcv() run."""

    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    bars_upserted: int = 0
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.symbols_failed == 0 and self.symbols_requested > 0


async def ingest_historical_ohlcv(
    symbols: List[str],
    start: datetime,
    end: datetime,
    provider: IMarketDataProvider,
    session_factory: Callable[[], Session],
) -> HistoricalIngestionResult:
    """Fetch and upsert every bar in [start, end] for each symbol.

    Each symbol is committed independently -- one symbol's failure
    does not roll back or block the others, matching ingest_ohlcv's
    same isolation guarantee.
    """
    result = HistoricalIngestionResult(symbols_requested=len(symbols))

    await provider.authenticate()

    for symbol in symbols:
        session = session_factory()
        try:
            bars = await provider.get_historical_ohlcv(symbol, start, end)
            stock = _get_or_create_stock(session, symbol)
            for bar in bars:
                _upsert_price_bar(session, stock, bar)
            session.commit()
            result.symbols_succeeded += 1
            result.bars_upserted += len(bars)
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error(
                "Failed to ingest historical OHLCV for symbol '%s': %s", symbol, exc
            )
        finally:
            session.close()

    await provider.disconnect()
    return result
