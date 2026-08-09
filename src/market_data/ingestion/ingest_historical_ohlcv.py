"""Incremental OHLCV ingestion: backfills a new symbol's history and
catches an already-tracked symbol up to today, using
IMarketDataProvider.get_historical_ohlcv() (a date-range call) instead
of ingest_ohlcv.py's single "latest bar" call.

This is the scheduler's primary OHLCV job (src.market_data.ingestion.
scheduler) -- it strictly generalizes ingest_ohlcv.py's job (a
zero-gap incremental catch-up naturally fetches just today's bar, the
trivial case), so the scheduler does not also run ingest_ohlcv.py
separately. ingest_ohlcv.py itself is untouched and still available for
its own documented "always just the latest bar" use case.

Idempotent and duplicate-safe like every other ingestion job in this
package: upsert_price_bar() re-upserts an already-ingested day's bar to
the same values rather than duplicating it, backed by PriceBar's own
(stock_id, timeframe, timestamp) unique constraint as the real
guarantee.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Timeframe
from src.market_data.ingestion._common import (
    IngestionResult,
    get_or_create_stock,
    is_quota_exhausted_for_today,
    sleep_if_rate_limited,
    upsert_price_bar,
)
from src.market_data.providers.market_data_provider import IMarketDataProvider

logger = logging.getLogger(__name__)


def _latest_bar_date(session: Session, stock_id: int) -> Optional[date]:
    latest_timestamp = (
        session.query(func.max(PriceBar.timestamp))
        .filter_by(stock_id=stock_id, timeframe=Timeframe.ONE_DAY)
        .scalar()
    )
    return latest_timestamp.date() if latest_timestamp is not None else None


async def ingest_historical_ohlcv(
    symbols: List[str],
    provider: IMarketDataProvider,
    session_factory: Callable[[], Session],
    backfill_days: int = 90,
) -> IngestionResult:
    """For each symbol: if bars already exist, fetch only from (the
    latest ingested day + 1) through today (incremental); if none exist
    yet, backfill the last `backfill_days` days (new symbol). A symbol
    already fully up to date (start date is in the future) is a
    success with zero rows fetched, not a failure or a no-op error.

    Each symbol is committed independently -- one symbol's failure
    (provider error, bad data) does not roll back or block the others,
    matching ingest_ohlcv.py/ingest_fundamentals.py's isolation.
    """
    result = IngestionResult(symbols_requested=len(symbols))
    today = datetime.now(timezone.utc).date()

    await provider.authenticate()

    for symbol in symbols:
        session = session_factory()
        try:
            stock = get_or_create_stock(session, symbol)
            latest = _latest_bar_date(session, stock.id)
            start = (
                latest + timedelta(days=1)
                if latest is not None
                else today - timedelta(days=backfill_days)
            )

            if start > today:
                session.commit()  # persist a freshly-created placeholder Stock row, if any
                result.symbols_succeeded += 1
                continue

            bars = await provider.get_historical_ohlcv(symbol, start, today)
            for bar in bars:
                upsert_price_bar(session, stock, bar)
                result.rows_upserted += 1
            if not bars and latest is None:
                # A genuinely new symbol (never had a single bar) whose
                # backfill window came back empty -- worth recording by
                # reason, since a bare "success" would otherwise hide
                # this from every diagnostic. Not an error: the provider
                # call itself succeeded, it just had nothing to report.
                result.zero_progress[symbol] = (
                    f"No OHLCV bars returned by provider for {start.isoformat()}..{today.isoformat()} "
                    "(symbol still has zero total price bars)."
                )
            session.commit()
            result.symbols_succeeded += 1
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error("Failed to ingest historical OHLCV for symbol '%s': %s", symbol, exc)
            if is_quota_exhausted_for_today(exc):
                logger.warning(
                    "ingest_historical_ohlcv: stopping early -- SAHMK daily quota exhausted, "
                    "remaining symbol(s) in this run not attempted."
                )
                break
            await sleep_if_rate_limited(exc)
        finally:
            session.close()

    await provider.disconnect()
    return result
