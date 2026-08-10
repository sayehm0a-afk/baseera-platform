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
from src.market_data.ingestion._common import (
    IngestionResult,
    get_or_create_stock,
    is_quota_exhausted_for_today,
    sleep_if_rate_limited,
)
from src.market_data.providers.fundamental_data_provider import IFundamentalDataProvider

logger = logging.getLogger(__name__)


def _deduplicate_by_ex_date(symbol: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """2026-08-09 production evidence: SAHMK's raw dividend "history" list
    occasionally carries more than one entry for the same ex_date (e.g.
    two entries, identical dividend_per_share, differing payment_date --
    a payment-date revision SAHMK's API returns alongside the original
    entry instead of replacing it). ex_date is this table's real business
    key (a company does not declare two distinct dividends sharing an
    ex-date; every real collision observed so far agreed on the amount),
    so this collapses each ex_date's raw entries to exactly one --
    deterministically, not "whichever happened to be inserted first" --
    before they ever reach the DB.

    This matters because the session factory here runs with
    autoflush=False (src/core/db/database.py): _upsert_dividend's
    "does this ex_date already exist" query only sees committed rows,
    not other pending session.add() calls from earlier in this same
    loop, so two raw entries sharing an ex_date would both be treated
    as new and collide on uq_dividend_identity at commit time -- exactly
    the failure production evidence showed."""
    with_ex_date: Dict[str, List[Dict[str, Any]]] = {}
    deduplicated: List[Dict[str, Any]] = []
    for record in records:
        ex_date = record.get("ex_date")
        if not ex_date:
            deduplicated.append(record)  # preserved as-is; existing no-ex_date skip logic handles it
            continue
        with_ex_date.setdefault(ex_date, []).append(record)

    for ex_date, group in with_ex_date.items():
        if len(group) == 1:
            deduplicated.append(group[0])
            continue
        amounts = {str(r.get("dividend_per_share")) for r in group}
        if len(amounts) > 1:
            logger.warning(
                "Dividend dedup for '%s' ex_date=%s: %d raw entries disagree on amount %s -- "
                "keeping the entry with the latest payment_date as a deterministic tie-break; "
                "this is a real provider-data anomaly, not fabricated.",
                symbol, ex_date, len(group), sorted(amounts),
            )
        # The entry with a real (non-null) payment_date wins over one with
        # none; among several real payment_dates, the latest is kept as the
        # most-recently-confirmed value -- deterministic given the same raw input.
        chosen = max(group, key=lambda r: (r.get("payment_date") is not None, r.get("payment_date") or ""))
        logger.info(
            "Dividend dedup for '%s' ex_date=%s: collapsed %d raw entries into 1 (payment_date=%s).",
            symbol, ex_date, len(group), chosen.get("payment_date"),
        )
        deduplicated.append(chosen)
    return deduplicated


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
            dividends = _deduplicate_by_ex_date(symbol, await get_dividends_fn(symbol))
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
            if is_quota_exhausted_for_today(exc):
                logger.warning(
                    "ingest_dividends: stopping early -- SAHMK daily quota exhausted, "
                    "remaining symbol(s) in this run not attempted."
                )
                break
            await sleep_if_rate_limited(exc)
        finally:
            session.close()

    await provider.disconnect()
    return result
