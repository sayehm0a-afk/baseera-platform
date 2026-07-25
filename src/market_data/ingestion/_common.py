"""Shared helpers for src.market_data.ingestion's job modules.

IngestionResult and get_or_create_stock were identically duplicated
across ingest_ohlcv.py and ingest_fundamentals.py (M2.1/M2.3) --
factored out here once, reused unchanged by those two (a
behavior-preserving refactor -- neither module's public contract or
logging text changed) and by every ingestion job added since
(symbols/historical-ohlcv/dividends). upsert_price_bar is new here (not
a refactor) -- both ingest_ohlcv.py and ingest_historical_ohlcv.py need
the identical single-bar upsert.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict

from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Stock, Timeframe

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary of one ingestion job run over a list of symbols."""

    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    rows_upserted: int = 0
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.symbols_failed == 0 and self.symbols_requested > 0


def get_or_create_stock(session: Session, symbol: str) -> Stock:
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


def upsert_price_bar(session: Session, stock: Stock, data: Dict) -> bool:
    """Upserts one OHLCV bar (the shape IMarketDataProvider.get_stock_data()/
    get_historical_ohlcv() both return) keyed by (stock_id, timeframe,
    timestamp) -- the same identity PriceBar's own unique constraint
    enforces, so this is safe to call repeatedly with the same bar
    (idempotent) and safe under concurrent ingestion runs (the
    constraint is the actual backstop, this is the common-case fast
    path). Returns True if a new row was inserted, False if an existing
    one was updated -- callers use this to count rows_upserted without
    caring which case it was."""
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
        return False

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
    return True
