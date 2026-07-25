"""SymbolSelector: resolves "every listed Saudi stock" to a concrete,
scannable symbol list -- reads only the already-ingested `Stock`/
`PriceBar` tables (via a plain SQLAlchemy query on the existing domain
models), never a market-data provider. Symbol *discovery* (finding out
what's listed on Tadawul/Nomu in the first place) is already
`sync_symbols`'s job (src/market_data/ingestion/ingest_symbols.py) --
this module reuses whatever `Stock` rows that ingestion job (or manual
seeding) has already produced, rather than duplicating provider-facing
directory logic.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from src.domain.models import PriceBar, Stock
from src.market_intelligence.config import get_scan_max_symbols, is_price_history_required_for_scan

logger = logging.getLogger(__name__)


class SymbolSelector:
    """`select()` returns every active `Stock.symbol`, in a stable
    (alphabetical) order. When `MARKET_SCAN_REQUIRE_PRICE_HISTORY` is
    true (the default), a symbol with zero ingested `PriceBar` rows is
    skipped here rather than being handed to the scanner only to come
    back as "insufficient data" -- the same "validates availability,
    skips unavailable symbols" requirement, resolved with one query
    instead of one failed pipeline run per symbol.
    """

    def select(self, session: Session, symbols: Optional[List[str]] = None) -> List[str]:
        if symbols is not None:
            # An explicit list (e.g. a REST caller scanning a subset)
            # bypasses discovery entirely, but still respects the same
            # bounded-workload ceiling as the full universe.
            return symbols[: get_scan_max_symbols()]

        query = session.query(Stock.symbol).filter(Stock.is_active.is_(True))

        if is_price_history_required_for_scan():
            symbols_with_bars = session.query(PriceBar.stock_id).distinct().subquery()
            query = query.filter(Stock.id.in_(session.query(symbols_with_bars.c.stock_id)))

        resolved = [row[0] for row in query.order_by(Stock.symbol).all()]

        max_symbols = get_scan_max_symbols()
        if len(resolved) > max_symbols:
            logger.warning(
                "SymbolSelector resolved %d active symbols, above MARKET_SCAN_MAX_SYMBOLS=%d -- "
                "truncating to the first %d alphabetically.",
                len(resolved), max_symbols, max_symbols,
            )
            resolved = resolved[:max_symbols]

        return resolved
