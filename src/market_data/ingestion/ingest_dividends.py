"""Dividend ingestion: pulls dividend history from a provider and
upserts it into the Dividend table, keyed by (stock_id, ex_date).

get_dividends(symbol) is not part of IFundamentalDataProvider --
SahmkFundamentalDataProvider and DevFundamentalDataProvider both expose
it as an extra method (the same "not every provider has this, check
before calling" pattern ingest_symbols.py uses for symbol discovery),
so a future IFundamentalDataProvider implementation that doesn't
support dividends degrades to "skip, logged," not a crash.

Idempotent and duplicate-safe like every other ingestion job: an
ex-date already ingested is updated in place, never duplicated, backed
by Dividend's own (stock_id, ex_date) unique constraint.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Dict, List

from sqlalchemy.orm import Session

from src.domain.models import Dividend, Stock
from src.market_data.ingestion._common import IngestionResult, get_or_create_stock
from src.market_data.providers.fundamental_data_provider import IFundamentalDataProvider

logger = logging.getLogger(__name__)


def _upsert_dividend(session: Session, stock: Stock, data: Dict[str, Any]) -> None:
    ex_date = date.fromisoformat(data["ex_date"])
    payment_date = date.fromisoformat(data["payment_date"]) if data.get("payment_date") else None

    existing = session.query(Dividend).filter_by(stock_id=stock.id, ex_date=ex_date).one_or_none()
    fields = dict(
        payment_date=payment_date,
        amount_per_share=Decimal(str(data["dividend_per_share"])),
        source=data.get("source", "unknown"),
        is_synthetic=bool(data.get("is_synthetic", False)),
    )

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return

    session.add(Dividend(stock_id=stock.id, ex_date=ex_date, **fields))


async def ingest_dividends(
    symbols: List[str],
    provider: IFundamentalDataProvider,
    session_factory: Callable[[], Session],
) -> IngestionResult:
    """Fetch and upsert each symbol's dividend history.

    Each symbol is committed independently -- one symbol's failure
    does not roll back or block the others. A record with no ex_date
    (the natural key) is skipped and logged, not fabricated.
    """
    result = IngestionResult(symbols_requested=len(symbols))
    await provider.authenticate()

    get_dividends_fn = getattr(provider, "get_dividends", None)
    if get_dividends_fn is None:
        logger.warning(
            "%s has no get_dividends() support -- skipping dividend ingestion entirely.",
            type(provider).__name__,
        )
        await provider.disconnect()
        return result

    for symbol in symbols:
        session = session_factory()
        try:
            dividends = await get_dividends_fn(symbol)
            stock = get_or_create_stock(session, symbol)
            for record in dividends:
                if not record.get("ex_date"):
                    logger.warning(
                        "Skipping a dividend record for '%s' with no ex_date.", symbol
                    )
                    continue
                _upsert_dividend(session, stock, record)
                result.rows_upserted += 1
            session.commit()
            result.symbols_succeeded += 1
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error("Failed to ingest dividends for symbol '%s': %s", symbol, exc)
        finally:
            session.close()

    await provider.disconnect()
    return result
