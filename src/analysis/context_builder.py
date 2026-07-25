"""build_analysis_context: assembles the technical/fundamental/live-
price inputs every downstream engine (`RecommendationEngine`,
`AIDecisionEngine`, `AnalystEngine`) consumes as one `AnalysisContext`.

Originally private to `src/api/routes/stocks.py` (shared there by
`/recommendation`, `/decision`, and `/analyst-report`); extracted here,
unchanged in behavior, so `src/market_intelligence/` can reuse the
exact same "run the two existing analysis engines against this
symbol's ingested data" work for a market-wide scan instead of
duplicating it -- the Phase 7 "no duplicate business logic" mandate,
applied to the one piece of orchestration every consumer of these
engines needs.

Deliberately takes an already-resolved `Stock` row, not a bare symbol
string -- looking a symbol up (and deciding what "not found" means for
the caller: an HTTP 404 for a REST route, a silently-skipped symbol
for a market scan) is the caller's concern, not this function's. This
also keeps this module free of any dependency on `src.api.*`, since it
lives in the engine layer, not the API layer.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.fundamental_loader import load_fundamental_snapshots
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.recommendation.types import AnalysisContext
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import PeriodType, Stock, Timeframe
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkError

logger = logging.getLogger(__name__)


async def build_analysis_context(
    stock: Stock,
    period_type: PeriodType,
    session: Session,
    market_provider: IMarketDataProvider,
) -> AnalysisContext:
    """Each leg degrades independently and gracefully: insufficient
    price history, no ingested fundamentals, or a provider outage on
    the live quote only omits that piece (`None`), never raises -- the
    caller decides whether the resulting context has enough to
    proceed."""
    symbol = stock.symbol

    technical_result = None
    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)
    try:
        technical_result = TechnicalAnalysisEngine().analyze(df)
    except ValueError as exc:
        logger.info("Technical leg unavailable for '%s': %s", symbol, exc)

    market_price: Optional[float] = None
    try:
        quote = await market_provider.get_stock_data(symbol)
        market_price = quote.get("close")
    except (SahmkError, CircuitBreakerOpenError) as exc:
        logger.info("Could not fetch a live price for '%s': %s", symbol, exc)

    fundamental_result = None
    snapshots = load_fundamental_snapshots(session, stock.id, period_type, limit=2)
    if snapshots:
        latest, prior = snapshots[0], (snapshots[1] if len(snapshots) > 1 else None)
        fundamental_result = FundamentalAnalysisEngine().analyze(
            latest, prior_facts=prior, market_price=market_price
        )

    return AnalysisContext(
        symbol=symbol,
        technical_result=technical_result,
        fundamental_result=fundamental_result,
        latest_price=market_price,
    )
