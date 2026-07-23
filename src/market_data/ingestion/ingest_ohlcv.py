"""OHLCV ingestion: pulls stock data from an IMarketDataProvider and
upserts it into the Stock/PriceBar tables.

Callable directly (not yet wired into RealWorker/RealTaskQueue --
that integration is out of M2.1's scope per the approved M2 blueprint,
which lists only this module's creation, not runtime-kernel wiring).
Its (task-dict-shaped) signature is deliberately compatible with
RealWorker.register_handler(task_type, handler) so a later milestone
can register it as a task handler without a redesign.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Dict, List

from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Stock, Timeframe
from src.market_data.providers.market_data_provider import IMarketDataProvider

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary of one ingest_ohlcv() run."""

    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.symbols_failed == 0 and self.symbols_requested > 0


def _get_or_create_stock(session: Session, symbol: str) -> Stock:
    stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
    if stock is not None:
        return stock

    logger.warning(
        "Creating placeholder Stock row for symbol '%s' with no reference data "
        "(name/sector) -- real reference data ingestion is a later milestone's "
        "concern, not this one's.",
        symbol,
    )
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}")
    session.add(stock)
    session.flush()  # assign stock.id without committing yet
    return stock


def _upsert_price_bar(session: Session, stock: Stock, data: Dict) -> None:
    timestamp = datetime.fromisoformat(data["timestamp"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    existing = (
        session.query(PriceBar)
        .filter_by(stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=timestamp)
        .one_or_none()
    )

    if existing is not None:
        existing.open = Decimal(str(data["open"]))
        existing.high = Decimal(str(data["high"]))
        existing.low = Decimal(str(data["low"]))
        existing.close = Decimal(str(data["close"]))
        existing.volume = int(data["volume"])
        return

    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=timestamp,
            open=Decimal(str(data["open"])),
            high=Decimal(str(data["high"])),
            low=Decimal(str(data["low"])),
            close=Decimal(str(data["close"])),
            volume=int(data["volume"]),
        )
    )


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
            stock = _get_or_create_stock(session, symbol)
            _upsert_price_bar(session, stock, data)
            session.commit()
            result.symbols_succeeded += 1
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error("Failed to ingest OHLCV for symbol '%s': %s", symbol, exc)
        finally:
            session.close()

    await provider.disconnect()
    return result
