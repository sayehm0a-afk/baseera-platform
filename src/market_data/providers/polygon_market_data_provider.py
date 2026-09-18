"""PolygonMarketDataProvider: the real, live IMarketDataProvider
implementation for US-market data, backed by Polygon.io's REST API.

Adapts src.market_data.polygon.service.PolygonMarketDataService (typed,
cached) to IMarketDataProvider's existing Dict[str, Any]-shaped
contract, unchanged, mirroring SahmkMarketDataProvider's own adapter
pattern (src.market_data.providers.sahmk_market_data_provider) exactly
-- only the vendor and market differ. Returned dicts carry
`source="polygon"` and `is_synthetic=False` instead of the sahmk/dev
markers.

Registered with MarketDataProviderFactory under "polygon" at import
time for future opt-in use -- NOT wired into provider_factory's live
selection logic in this phase (that module's own selection code is
left completely untouched). Every existing Tadawul/SAHMK code path is
unaffected by this file's existence, and constructing this class makes
no network call and never raises, even with no POLYGON_API_KEY
configured at all.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.polygon.client import PolygonClient
from src.market_data.polygon.exceptions import (
    PolygonAuthenticationError,
    PolygonConfigurationError,
    PolygonError,
)
from src.market_data.polygon.service import PolygonMarketDataService
from src.market_data.providers.market_data_provider import (
    IMarketDataProvider,
    MarketDataProviderFactory,
    ProviderHealth,
)

logger = logging.getLogger(__name__)

# Maps IMarketDataProvider's generic `interval` strings to Polygon's own
# (multiplier, timespan) aggregate-window parameters.
_INTERVAL_TO_POLYGON: Dict[str, Tuple[int, str]] = {
    "1m": (1, "minute"),
    "5m": (5, "minute"),
    "15m": (15, "minute"),
    "30m": (30, "minute"),
    "1h": (1, "hour"),
    "1d": (1, "day"),
    "1w": (1, "week"),
}


def _polygon_multiplier_timespan(interval: str) -> Tuple[int, str]:
    """Raises ValueError for an interval this integration has no
    mapping for, rather than guessing at one."""
    try:
        return _INTERVAL_TO_POLYGON[interval]
    except KeyError:
        raise ValueError(f"Unsupported interval '{interval}' for Polygon aggregates.") from None


class PolygonMarketDataProvider(IMarketDataProvider):
    """Live market data provider backed by the Polygon.io API for
    US-listed (Nasdaq/NYSE) symbols.

    Constructor signature matches MarketDataProviderFactory's common
    `(api_endpoint, api_key, **kwargs)` shape; either may be omitted to
    fall back to POLYGON_BASE_URL/POLYGON_API_KEY from the environment
    (src.market_data.config) -- never a hardcoded value.
    """

    is_synthetic = False

    def __init__(self, api_endpoint: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self._service = PolygonMarketDataService(
            client=PolygonClient(api_key=api_key, base_url=api_endpoint),
            cache=TTLCache(),
        )
        self.authenticated = False

    async def authenticate(self) -> bool:
        """Verifies the configured key against the cheapest confirmed
        Polygon endpoint (GET /v1/marketstatus/now -- it requires no
        entitlement beyond a valid key). Swallows every
        PolygonError/CircuitBreakerOpenError into a plain bool,
        mirroring SahmkMarketDataProvider.authenticate()'s exact
        contract."""
        if not self._service.has_credentials:
            logger.warning(
                "PolygonMarketDataProvider.authenticate(): POLYGON_API_KEY is not configured."
            )
            self.authenticated = False
            return False

        try:
            self.authenticated = await self.check_connectivity()
        except (PolygonAuthenticationError, PolygonConfigurationError) as exc:
            logger.error("Polygon authentication failed: %s", exc)
            self.authenticated = False
        except (PolygonError, CircuitBreakerOpenError) as exc:
            logger.error("Polygon authentication check could not complete: %s", exc)
            self.authenticated = False

        return self.authenticated

    async def check_connectivity(self) -> bool:
        """Same underlying probe as authenticate(), but *raises*
        instead of swallowing PolygonError/CircuitBreakerOpenError --
        mirrors SahmkMarketDataProvider.check_connectivity()'s exact
        contract, for a future connectivity-probe caller."""
        await self._service.get_market_status()
        return True

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Most recent daily OHLCV bar via GET
        /v2/aggs/ticker/{symbol}/range/1/day/..."""
        bar = await self._service.get_daily_bar(symbol)
        return {
            "symbol": bar.ticker,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "timestamp": bar.timestamp.isoformat(),
            "source": "polygon",
            "is_synthetic": False,
        }

    async def get_historical_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> List[Dict[str, Any]]:
        """A range of OHLCV bars via GET
        /v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}."""
        multiplier, timespan = _polygon_multiplier_timespan(interval)
        bars = await self._service.get_aggregates(
            symbol, start, end, multiplier=multiplier, timespan=timespan
        )
        return [
            {
                "symbol": bar.ticker,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "timestamp": bar.timestamp.isoformat(),
                "source": "polygon",
                "is_synthetic": False,
            }
            for bar in bars
        ]

    async def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """Most recent close via GET /v2/aggs/ticker/{symbol}/prev. Not
        part of IMarketDataProvider -- exposed for callers that only
        need a current price, mirroring
        SahmkMarketDataProvider.get_latest_quote(). Polygon's Free tier
        has no true real-time last-trade endpoint verified for this
        integration, so this is the prior trading day's close, not an
        intraday price."""
        bar = await self._service.get_previous_close(symbol)
        return {
            "symbol": bar.ticker,
            "price": bar.close,
            "change": None,
            "change_percent": None,
            "volume": bar.volume,
            "timestamp": bar.timestamp.isoformat(),
            "source": "polygon",
            "is_synthetic": False,
        }

    async def get_ticker_details(self, symbol: str) -> Dict[str, Any]:
        """Reference metadata via GET /v3/reference/tickers/{symbol}.
        Not part of IMarketDataProvider -- exposed opportunistically,
        mirroring SahmkMarketDataProvider.get_company_profile()."""
        details = await self._service.get_ticker_details(symbol)
        return {
            "symbol": details.ticker,
            "name": details.name,
            "market": details.market,
            "primary_exchange": details.primary_exchange,
            "type": details.type,
            "active": details.active,
            "currency_name": details.currency_name,
            "market_cap": details.market_cap,
            "source": "polygon",
            "is_synthetic": False,
        }

    async def get_symbol_directory(self) -> List[Dict[str, Any]]:
        """The active US stock ticker directory via GET
        /v3/reference/tickers. Not part of IMarketDataProvider --
        exposed opportunistically, mirroring
        SahmkMarketDataProvider.get_symbol_directory()."""
        tickers = await self._service.get_ticker_directory()
        return [
            {
                "symbol": t.ticker,
                "name": t.name,
                "market": t.market,
                "primary_exchange": t.primary_exchange,
                "type": t.type,
                "active": t.active,
                "source": "polygon",
                "is_synthetic": False,
            }
            for t in tickers
        ]

    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        """Best-effort index snapshot via GET
        /v2/aggs/ticker/{index_name}/prev.

        Polygon's Free/Starter tiers have no dedicated real-time
        index-value endpoint verified for this integration --
        `index_name` is passed straight through as a ticker symbol
        (e.g. "SPY" for the S&P 500 ETF proxy), the closest confirmed,
        actually-callable Polygon endpoint for "what is this index
        doing." Not a substitute for a real index-level feed if/when
        one is added."""
        bar = await self._service.get_previous_close(index_name)
        return {
            "index_name": index_name,
            "value": bar.close,
            "change": None,
            "change_percent": None,
            "timestamp": bar.timestamp.isoformat(),
            "source": "polygon",
            "is_synthetic": False,
        }

    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Recent news via GET /v2/reference/news (no `ticker` filter --
        market-wide)."""
        news_items = await self._service.get_ticker_news(limit=limit)
        return [
            {
                "headline": item.title,
                "symbol": item.tickers[0] if item.tickers else None,
                "timestamp": (
                    item.published_utc.isoformat()
                    if item.published_utc
                    else datetime.now(timezone.utc).isoformat()
                ),
                "source": "polygon",
                "is_synthetic": False,
            }
            for item in news_items
        ]

    async def health_check(self) -> ProviderHealth:
        if not self._service.has_credentials:
            return ProviderHealth.UNHEALTHY
        try:
            healthy = await self._service.check_health()
        except CircuitBreakerOpenError:
            return ProviderHealth.UNHEALTHY
        return ProviderHealth.HEALTHY if healthy else ProviderHealth.UNHEALTHY

    async def disconnect(self) -> None:
        await self._service.close()
        self.authenticated = False


MarketDataProviderFactory.register("polygon", PolygonMarketDataProvider)
