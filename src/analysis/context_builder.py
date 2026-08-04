"""build_analysis_context: assembles the technical/fundamental/live-
price/news-sentiment inputs every downstream engine
(`RecommendationEngine`, `AIDecisionEngine`, `AnalystEngine`) consumes
as one `AnalysisContext`.

Originally private to `src/api/routes/stocks.py` (shared there by
`/recommendation`, `/decision`, and `/analyst-report`); extracted here,
unchanged in behavior, so `src/market_intelligence/` and
`src/portfolio_intelligence/` can reuse the exact same "run the
existing analysis engines against this symbol's ingested data" work
instead of duplicating it -- the Phase 7 "no duplicate business logic"
mandate, applied to the one piece of orchestration every consumer of
these engines needs. This is also the single hook point Phase 12's
News Intelligence Engine uses to reach every one of those consumers at
once (see the `news_service` leg below) -- populating `extra` here,
with zero changes required at any of the four call sites, is what
makes "the recommendation must automatically change when important
news appears" true without a second, parallel recommendation path.

Deliberately takes an already-resolved `Stock` row, not a bare symbol
string -- looking a symbol up (and deciding what "not found" means for
the caller: an HTTP 404 for a REST route, a silently-skipped symbol
for a market scan) is the caller's concern, not this function's. This
also keeps this module free of any dependency on `src.api.*`, since it
lives in the engine layer, not the API layer.
"""

import logging
from typing import Any, Dict, Optional

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
from src.news_intelligence.service import NewsIntelligenceService

logger = logging.getLogger(__name__)


def _news_sentiment_extra(session: Session, symbol: str, news_service: NewsIntelligenceService) -> Dict[str, Any]:
    """A cheap, synchronous, DB-only read (see
    `NewsIntelligenceService.get_symbol_sentiment`'s own docstring for
    why it never touches the network or an LLM) -- degrades exactly
    like every other leg here: no persisted, analyzed news for this
    symbol simply means an empty `extra`, never a raised exception or
    a fabricated sentiment value."""
    try:
        sentiment = news_service.get_symbol_sentiment(session, symbol)
    except Exception as exc:  # noqa: BLE001 -- a news-read failure must never break the whole context
        logger.info("News sentiment leg unavailable for '%s': %s", symbol, exc)
        return {}
    if sentiment is None:
        return {}
    return {
        "news_sentiment": {
            "sentiment_score": sentiment.sentiment_score,
            "article_count": sentiment.article_count,
            "events": [
                {
                    "news_event_id": event.news_event_id,
                    "headline": event.headline,
                    "category": event.category.value,
                    "sentiment_score": event.sentiment_score,
                    "confidence": event.confidence,
                    "impact_points": event.impact_points,
                }
                for event in sentiment.events
            ],
        }
    }


async def build_analysis_context(
    stock: Stock,
    period_type: PeriodType,
    session: Session,
    market_provider: IMarketDataProvider,
    news_service: Optional[NewsIntelligenceService] = None,
) -> AnalysisContext:
    """Each leg degrades independently and gracefully: insufficient
    price history, no ingested fundamentals, a provider outage on the
    live quote, or no analyzed news for this symbol only omits that
    piece, never raises -- the caller decides whether the resulting
    context has enough to proceed. `news_service` defaults to a fresh
    `NewsIntelligenceService()` (safe to construct even with no
    `OPENAI_API_KEY` configured -- it only degrades to "analysis
    unavailable," it never raises); pass one explicitly to reuse an
    instance across many symbols in one request (e.g. a market scan or
    a portfolio) instead of constructing one per symbol."""
    symbol = stock.symbol

    technical_result = None
    df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)
    try:
        technical_result = TechnicalAnalysisEngine().analyze(df)
    except ValueError as exc:
        logger.info("Technical leg unavailable for '%s': %s", symbol, exc)

    market_price: Optional[float] = None
    quote_extra: Dict[str, Any] = {}
    get_latest_quote = getattr(market_provider, "get_latest_quote", None)
    if get_latest_quote is not None:
        # Live quote (GET /quote/{symbol}/) is the correct source for the
        # *current* price during market hours -- unlike get_stock_data()'s
        # completed daily bar, which does not exist yet until the session
        # settles and is always at least one bar stale while trading is
        # live. Not part of IMarketDataProvider (DevMarketDataProvider has
        # no live quote to serve), so this leg is opportunistic via getattr,
        # matching the same pattern ingest_symbols.py uses for
        # get_company_profile/get_symbol_directory.
        try:
            quote = await get_latest_quote(symbol)
            market_price = quote.get("price")
            quote_extra = {
                "quote": {
                    "price": quote.get("price"),
                    "change": quote.get("change"),
                    "change_percent": quote.get("change_percent"),
                    "timestamp": quote.get("timestamp"),
                    "source": quote.get("source"),
                    "is_synthetic": quote.get("is_synthetic"),
                }
            }
        except (SahmkError, CircuitBreakerOpenError) as exc:
            logger.info("Could not fetch a live quote for '%s': %s", symbol, exc)

    if market_price is None:
        # Fallback: today's completed daily bar (or the live provider is
        # unavailable / a dev provider with no live-quote support).
        try:
            bar = await market_provider.get_stock_data(symbol)
            market_price = bar.get("close")
            quote_extra = {
                "quote": {
                    "price": bar.get("close"),
                    "change": None,
                    "change_percent": None,
                    "timestamp": bar.get("timestamp"),
                    "source": bar.get("source"),
                    "is_synthetic": bar.get("is_synthetic"),
                }
            }
        except (SahmkError, CircuitBreakerOpenError) as exc:
            logger.info("Could not fetch a live price for '%s': %s", symbol, exc)

    fundamental_result = None
    snapshots = load_fundamental_snapshots(session, stock.id, period_type, limit=2)
    if snapshots:
        latest, prior = snapshots[0], (snapshots[1] if len(snapshots) > 1 else None)
        fundamental_result = FundamentalAnalysisEngine().analyze(
            latest, prior_facts=prior, market_price=market_price
        )

    news_service = news_service if news_service is not None else NewsIntelligenceService()
    extra = {**quote_extra, **_news_sentiment_extra(session, symbol, news_service)}

    return AnalysisContext(
        symbol=symbol,
        technical_result=technical_result,
        fundamental_result=fundamental_result,
        latest_price=market_price,
        extra=extra,
    )
