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

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict

from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Stock, Timeframe

logger = logging.getLogger(__name__)

_MAX_RATE_LIMIT_PAUSE_SECONDS = 30.0


async def sleep_if_rate_limited(exc: Exception) -> None:
    """If `exc` carries a real, server-provided Retry-After hint
    (SahmkRateLimitError.retry_after, set once SahmkClient's own
    3-attempt retry is exhausted on a 429), sleeps for that long --
    capped at _MAX_RATE_LIMIT_PAUSE_SECONDS so a large or malformed
    value can never stall a job for an unbounded time -- before the
    caller's per-symbol loop moves on to the next symbol.

    Without this, a genuine SAHMK rate-limit response was followed
    immediately by the very next symbol's request, with nothing in any
    ingestion job actually backing off at the job level -- fine at
    ~100 symbols, but exactly the kind of gap that turns one real 429
    into dozens of consecutive symbol failures once a run covers ~400
    symbols. A no-op for any other exception (no retry_after
    attribute, or None)."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is None:
        return
    delay = min(max(float(retry_after), 0.0), _MAX_RATE_LIMIT_PAUSE_SECONDS)
    if delay > 0:
        logger.warning(
            "Rate-limited by SAHMK (retry_after=%.1fs) -- pausing %.1fs before the next symbol.",
            retry_after,
            delay,
        )
        await asyncio.sleep(delay)


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

    source = data.get("source", "unknown")
    is_synthetic = data.get("is_synthetic", True)

    if existing is not None:
        existing.open = Decimal(str(data["open"]))
        existing.high = Decimal(str(data["high"]))
        existing.low = Decimal(str(data["low"]))
        existing.close = Decimal(str(data["close"]))
        existing.volume = int(data["volume"])
        existing.source = source
        existing.is_synthetic = is_synthetic
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
            source=source,
            is_synthetic=is_synthetic,
        )
    )
    return True
