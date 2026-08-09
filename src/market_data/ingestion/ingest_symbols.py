"""Market-symbol reference-data ingestion: keeps Stock rows (symbol/
name/sector) up to date.

Two ways a symbol enters the sync set:
1. Explicitly configured (the `symbols` argument -- typically
   INGESTION_SYMBOL_UNIVERSE from src.market_data.ingestion.config).
2. Auto-discovered (`discover_all=True`) via the provider's full
   Tadawul+Nomu symbol directory, if it exposes one -- currently only
   SahmkMarketDataProvider.get_symbol_directory() (DevMarketDataProvider
   has no real universe to discover). This is deliberately ONE request
   for the whole directory, not one per symbol -- SAHMK's own directory
   response already carries name/sector per entry, so no per-symbol
   follow-up call is needed for discovered symbols.

Idempotent like every other ingestion job: re-running with unchanged
provider data upserts the same values, and Stock.symbol's own unique
constraint is the real duplicate-prevention backstop.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import Stock
from src.market_data.ingestion._common import (
    UNCLASSIFIED_BUCKET,
    IngestionResult,
    get_or_create_stock,
    is_quota_exhausted_for_today,
    sleep_if_rate_limited,
)
from src.market_data.providers.market_data_provider import IMarketDataProvider

logger = logging.getLogger(__name__)


def _apply_entry(stock: Stock, entry: Dict[str, Any]) -> bool:
    """Updates stock.name_en/name_ar/sector from a directory/profile
    entry. Returns True iff something actually changed.

    `is_eligible` (present only on SahmkMarketDataProvider.get_symbol_
    directory() entries, via universe_policy.classify_universe) marks
    a non-equity instrument -- ETF, REIT, sukuk, rights issue,
    suspended/delisted -- inactive so SymbolSelector (which filters on
    Stock.is_active) never scans it as if it were a common stock. Absent
    on a plain get_company_profile() lookup for one explicit symbol;
    `stock.is_active` is left at its existing/default value (True) in
    that case, matching prior behavior exactly."""
    changed = False
    is_eligible = entry.get("is_eligible")
    if is_eligible is not None and stock.is_active != bool(is_eligible):
        stock.is_active = bool(is_eligible)
        changed = True
    if "instrument_bucket" in entry and stock.instrument_bucket != entry["instrument_bucket"]:
        stock.instrument_bucket = entry["instrument_bucket"]
        changed = True
    if "exclusion_reason" in entry and stock.exclusion_reason != entry["exclusion_reason"]:
        stock.exclusion_reason = entry["exclusion_reason"]
        changed = True
    name = entry.get("name")
    if name and stock.name_en != name:
        stock.name_en = name
        changed = True
    name_ar = entry.get("name_ar")
    if name_ar and stock.name_ar != name_ar:
        logger.info("Populated name_ar for symbol '%s' from real SAHMK data: %r", stock.symbol, name_ar)
        stock.name_ar = name_ar
        changed = True
    sector = entry.get("sector")
    if sector and stock.sector != sector:
        stock.sector = sector
        changed = True
    industry = entry.get("industry")
    if industry and stock.industry != industry:
        stock.industry = industry
        changed = True
    exchange = entry.get("exchange")
    if exchange and stock.exchange != exchange:
        stock.exchange = exchange
        changed = True
    return changed


_QUARANTINE_REASON = (
    "Unclassified Stock row absent from the most recent full SAHMK directory "
    "discovery pass and not part of the explicitly configured symbol universe -- "
    "identity/instrument-type could not be confirmed, so it is quarantined "
    "(is_active=False) rather than left silently active."
)


def _quarantine_unresolved_stocks(session: Session, target_symbols: set) -> int:
    """Part of the single-authority universe-classification policy: any
    Stock row that was never classified by universe_policy.classify_
    universe() (instrument_bucket is null or the UNCLASSIFIED_UNRESOLVED
    placeholder bucket) and is absent from this full discovery pass's
    target symbol set -- i.e. SAHMK's live directory doesn't currently
    know it and it isn't an operator-curated explicit symbol either --
    is marked inactive and quarantined instead of being left as a
    silently-active, unverified stub. Only ever called with
    discover_all=True and a non-empty directory_entries (a real,
    successful directory fetch), so "absent from target_symbols" means
    "absent from a real, current SAHMK snapshot," not "the fetch
    failed."""
    rows = (
        session.query(Stock)
        .filter(Stock.symbol.notin_(target_symbols))
        .filter(Stock.is_active.is_(True))
        .filter((Stock.instrument_bucket.is_(None)) | (Stock.instrument_bucket == UNCLASSIFIED_BUCKET))
        .all()
    )
    for stock in rows:
        stock.is_active = False
        stock.instrument_bucket = UNCLASSIFIED_BUCKET
        stock.exclusion_reason = _QUARANTINE_REASON
        logger.warning(
            "Quarantined unresolved Stock '%s' (name_en=%r): absent from SAHMK directory, never classified.",
            stock.symbol, stock.name_en,
        )
    if rows:
        session.commit()
    return len(rows)


async def sync_symbols(
    symbols: List[str],
    provider: IMarketDataProvider,
    session_factory: Callable[[], Session],
    discover_all: bool = False,
) -> IngestionResult:
    """Ensures a Stock row exists, with fresh name/sector where the
    provider can supply it, for every symbol in `symbols` (plus every
    symbol the provider's directory reports, if discover_all=True and
    supported). Each symbol is committed independently -- one symbol's
    failure does not roll back or block the others.

    `symbols` (the operator's own explicitly-configured seed list, e.g.
    INGESTION_SYMBOL_UNIVERSE) is the one trusted source that may create
    a new Stock row as active-by-default before real classification
    exists (see get_or_create_stock's `trusted` parameter) -- everything
    else defaults unclassified/inactive until universe_policy.
    classify_universe() (via the directory pass below) confirms it.
    """
    result = IngestionResult()
    await provider.authenticate()

    explicit_symbols = set(symbols)
    directory_entries: Dict[str, Dict[str, Any]] = {}
    if discover_all:
        directory_fn = getattr(provider, "get_symbol_directory", None)
        if directory_fn is None:
            logger.info(
                "sync_symbols(discover_all=True): %s has no symbol-directory support -- "
                "skipping discovery, syncing only the explicitly configured symbols.",
                type(provider).__name__,
            )
        else:
            try:
                for entry in await directory_fn():
                    directory_entries[entry["symbol"]] = entry
            except Exception as exc:
                logger.error("Symbol directory discovery failed, continuing without it: %s", exc)

    # dict.fromkeys() dedupes while preserving order -- explicit symbols
    # first, then anything discovery reported that wasn't already there.
    target_symbols = list(dict.fromkeys(list(symbols) + list(directory_entries.keys())))
    result.symbols_requested = len(target_symbols)

    for symbol in target_symbols:
        session = session_factory()
        try:
            stock = get_or_create_stock(session, symbol, trusted=symbol in explicit_symbols)
            entry: Optional[Dict[str, Any]] = directory_entries.get(symbol)
            if entry is None:
                profile_fn = getattr(provider, "get_company_profile", None)
                if profile_fn is not None:
                    entry = await profile_fn(symbol)
            if entry is not None and _apply_entry(stock, entry):
                result.rows_upserted += 1
            session.commit()
            result.symbols_succeeded += 1
        except Exception as exc:
            session.rollback()
            result.symbols_failed += 1
            result.errors[symbol] = str(exc)
            logger.error("Failed to sync symbol '%s': %s", symbol, exc)
            if is_quota_exhausted_for_today(exc):
                logger.warning(
                    "sync_symbols: stopping early -- %d of %d symbol(s) not attempted "
                    "(SAHMK daily quota exhausted).",
                    len(target_symbols) - target_symbols.index(symbol) - 1,
                    len(target_symbols),
                )
                break
            await sleep_if_rate_limited(exc)
        finally:
            session.close()

    if discover_all and directory_entries:
        session = session_factory()
        try:
            quarantined = _quarantine_unresolved_stocks(session, set(target_symbols))
            if quarantined:
                logger.warning("sync_symbols: quarantined %d unresolved Stock row(s) this pass.", quarantined)
        finally:
            session.close()

    await provider.disconnect()
    return result
