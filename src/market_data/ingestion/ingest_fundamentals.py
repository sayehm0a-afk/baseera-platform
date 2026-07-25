"""Fundamentals ingestion: pulls financial-statement data from an
IFundamentalDataProvider and upserts it into the Stock/FundamentalSnapshot
tables.

Callable directly (not yet wired into RealWorker/RealTaskQueue --
same deliberate exclusion as ingest_ohlcv.py, M2.1). Mirrors
ingest_ohlcv.py's structure and per-symbol failure isolation exactly.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import FundamentalSnapshot, PeriodType, Stock
from src.market_data.ingestion._common import IngestionResult, get_or_create_stock
from src.market_data.providers.fundamental_data_provider import IFundamentalDataProvider

logger = logging.getLogger(__name__)


def _decimal_or_none(value) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _upsert_fundamental_snapshot(session: Session, stock: Stock, data: Dict) -> None:
    period_type = PeriodType(data["period_type"])
    fiscal_period_end = date.fromisoformat(data["fiscal_period_end"])

    existing = (
        session.query(FundamentalSnapshot)
        .filter_by(stock_id=stock.id, period_type=period_type, fiscal_period_end=fiscal_period_end)
        .one_or_none()
    )

    fields = dict(
        revenue=Decimal(str(data["revenue"])),
        gross_profit=_decimal_or_none(data.get("gross_profit")),
        net_income=Decimal(str(data["net_income"])),
        total_assets=Decimal(str(data["total_assets"])),
        total_liabilities=Decimal(str(data["total_liabilities"])),
        total_equity=Decimal(str(data["total_equity"])),
        current_assets=Decimal(str(data["current_assets"])),
        current_liabilities=Decimal(str(data["current_liabilities"])),
        inventory=_decimal_or_none(data.get("inventory")),
        cash_and_equivalents=_decimal_or_none(data.get("cash_and_equivalents")),
        total_debt=_decimal_or_none(data.get("total_debt")),
        shares_outstanding=int(data["shares_outstanding"]),
        eps=Decimal(str(data["eps"])),
        dividend_per_share=Decimal(str(data.get("dividend_per_share", 0))),
        source=data.get("source", "unknown"),
        is_synthetic=bool(data.get("is_synthetic", False)),
    )

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return

    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=period_type,
            fiscal_period_end=fiscal_period_end,
            **fields,
        )
    )


async def ingest_fundamentals(
    symbols: List[str],
    provider: IFundamentalDataProvider,
    session_factory: Callable[[], Session],
    period_type: str = "annual",
) -> IngestionResult:
    """Fetch and upsert one financial-statement snapshot per symbol.

    Each symbol is committed independently -- one symbol's failure
    (provider error, bad data) does not roll back or block the others.
    """
    result = IngestionResult(symbols_requested=len(symbols))

    await provider.authenticate()

    for symbol in symbols:
        session = session_factory()
        try:
            data = await provider.get_fundamentals(symbol, period_type=period_type)
            stock = get_or_create_stock(session, symbol)
            _upsert_fundamental_snapshot(session, stock, data)
            session.commit()
            result.symbols_succeeded += 1
            result.rows_upserted += 1
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error("Failed to ingest fundamentals for symbol '%s': %s", symbol, exc)
        finally:
            session.close()

    await provider.disconnect()
    return result
