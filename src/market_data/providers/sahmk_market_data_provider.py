"""SahmkMarketDataProvider: the real, live IMarketDataProvider
implementation, backed by SAHMK (sahmk.sa) -- a Tadawul-licensed Saudi
market data vendor.

Adapts src.market_data.sahmk.service.SahmkMarketDataService (typed,
cached) to IMarketDataProvider's existing Dict[str, Any]-shaped
contract, unchanged, so ingest_ohlcv.py and every other caller written
against DevMarketDataProvider work identically against this provider --
only the data stops being synthetic. Returned dicts mirror
DevMarketDataProvider's shape exactly (same keys), with
`source="sahmk"` and `is_synthetic=False` instead of the dev markers.

See docs/SAHMK_INTEGRATION.md for the verified API contract this class
implements against.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.providers.market_data_provider import (
    IMarketDataProvider,
    MarketDataProviderFactory,
    ProviderHealth,
)
from src.market_data.sahmk.client import SahmkClient
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkEntitlementError,
    SahmkError,
)
from src.market_data.sahmk.service import SahmkMarketDataService
from src.market_intelligence.universe_policy import UniverseClassificationResult, classify_universe

logger = logging.getLogger(__name__)


class SahmkMarketDataProvider(IMarketDataProvider):
    """Live market data provider backed by the SAHMK API.

    Constructor signature matches MarketDataProviderFactory's common
    `(api_endpoint, api_key, **kwargs)` shape; either may be omitted to
    fall back to SAHMK_BASE_URL/SAHMK_API_KEY from the environment
    (src.market_data.config) -- never a hardcoded value.
    """

    is_synthetic = False

    def __init__(self, api_endpoint: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self._service = SahmkMarketDataService(
            client=SahmkClient(api_key=api_key, base_url=api_endpoint)
        )
        self.authenticated = False
        self.last_universe_classification: Optional[UniverseClassificationResult] = None

    @property
    def last_directory_diagnostics(self):
        """Proxies SahmkMarketDataService.last_directory_diagnostics --
        real pagination evidence (pages fetched, whether a next/count/
        total signal was ever present in the raw /companies/ response,
        the raw envelope's top-level keys) from the last
        get_company_directory() call. None until that has run at least
        once. This was computed by the service since the pagination-
        following fix but never read by any caller -- exposed here so
        admin diagnostics can answer "is ~100 a pagination limit or the
        real universe?" with real evidence instead of a guess."""
        return self._service.last_directory_diagnostics

    async def authenticate(self) -> bool:
        """Verifies the configured key against the cheapest confirmed
        SAHMK endpoint (GET /market/summary/). SAHMK has no
        token-exchange step -- the key is either accepted or it isn't.

        A confirmed-valid-but-plan-limited key (SahmkEntitlementError,
        403 PLAN_LIMIT) still counts as authenticated: the credential
        itself is correct, only a specific endpoint is out of plan.

        Swallows every SahmkError/CircuitBreakerOpenError into a plain
        bool -- provider_factory's connectivity-probe retry needs to
        distinguish *why* this failed (transient vs. permanent) and
        calls check_connectivity() directly instead; see that method's
        docstring."""
        if not self._service.has_credentials:
            logger.warning(
                "SahmkMarketDataProvider.authenticate(): SAHMK_API_KEY is not configured."
            )
            self.authenticated = False
            return False

        try:
            self.authenticated = await self.check_connectivity()
        except (SahmkAuthenticationError, SahmkConfigurationError) as exc:
            logger.error("SAHMK authentication failed: %s", exc)
            self.authenticated = False
        except (SahmkError, CircuitBreakerOpenError) as exc:
            logger.error("SAHMK authentication check could not complete: %s", exc)
            self.authenticated = False

        return self.authenticated

    async def check_connectivity(self) -> bool:
        """Same underlying probe as authenticate(), but *raises*
        instead of swallowing SahmkError/CircuitBreakerOpenError --
        used by provider_factory's bounded connectivity-probe retry
        (src.market_data.provider_connectivity_retry), which needs the
        real exception type to tell a transient failure (timeout, 429,
        5xx, network) apart from a permanent one (401, missing key)
        before deciding whether to retry."""
        try:
            await self._service.get_index_snapshot("TASI")
            return True
        except SahmkEntitlementError:
            return True

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Today's OHLCV bar via GET /historical/{symbol}/ -- not
        /quote/, which has no open/high/low fields (see
        docs/SAHMK_INTEGRATION.md)."""
        bar = await self._service.get_daily_bar(symbol)
        return {
            "symbol": bar.symbol,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "timestamp": (bar.timestamp or datetime.now(timezone.utc)).isoformat(),
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def get_historical_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> List[Dict[str, Any]]:
        """A range of OHLCV bars via GET /historical/{symbol}/ --
        the same endpoint get_stock_data() uses for a single day,
        generalized to a date range for ingestion backfill."""
        bars = await self._service.get_historical_bars(symbol, start, end, interval=interval)
        return [
            {
                "symbol": bar.symbol,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "timestamp": (bar.timestamp or datetime.now(timezone.utc)).isoformat(),
                "source": "sahmk",
                "is_synthetic": False,
            }
            for bar in bars
        ]

    async def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """Live price via GET /quote/{symbol}/. Not part of
        IMarketDataProvider -- exposed for callers that only need a
        current price and don't need a full OHLCV bar."""
        quote = await self._service.get_latest_quote(symbol)
        return {
            "symbol": quote.symbol,
            "price": quote.price,
            "change": quote.change,
            "change_percent": quote.change_percent,
            "volume": quote.volume,
            "timestamp": quote.timestamp.isoformat(),
            "source": "sahmk",
            "is_synthetic": False,
            "bid": quote.bid,
            "ask": quote.ask,
        }

    async def get_symbol_directory(self) -> List[Dict[str, Any]]:
        """The full Tadawul+Nomu symbol directory via GET /companies/.
        Not part of IMarketDataProvider -- DevMarketDataProvider has no
        real "discovery" concept, so this is opportunistic: callers
        (ingest_symbols.py) check for this method's presence rather
        than assuming every provider has it.

        Every entry is run through `universe_policy.classify_universe`
        (deny-list: ETFs/REITs/sukuk/rights/suspended/delisted excluded,
        everything else eligible) and carries `is_eligible` +
        `instrument_bucket` so ingest_symbols.sync_symbols can mark a
        non-equity instrument's Stock row inactive instead of scanning
        it as if it were a common stock. `self.last_universe_classification`
        keeps the full breakdown (bucket counts, distinct observed field
        values) for admin/coverage reporting -- the same "record real
        diagnostics for the last real call" pattern
        SahmkMarketDataService.last_directory_diagnostics already uses."""
        companies = await self._service.get_company_directory()
        classification: UniverseClassificationResult = classify_universe(companies)
        self.last_universe_classification = classification
        eligible_symbols = set(classification.eligible_symbols)
        detail_by_symbol = {c.symbol: c for c in classification.classifications}
        return [
            {
                "symbol": c.symbol,
                "name": c.name,
                "name_ar": c.name_ar,
                "sector": c.sector,
                "industry": c.industry,
                "exchange": c.exchange,
                "source": "sahmk",
                "is_synthetic": False,
                "is_eligible": c.symbol in eligible_symbols,
                "instrument_bucket": detail_by_symbol[c.symbol].bucket if c.symbol in detail_by_symbol else None,
                "exclusion_reason": (
                    detail_by_symbol[c.symbol].exclusion_reason if c.symbol in detail_by_symbol else None
                ),
            }
            for c in companies
        ]

    async def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Company profile via GET /company/{symbol}/. Not part of
        IMarketDataProvider -- exposed opportunistically for
        ingest_symbols.sync_symbols(), which enriches a Stock's
        name/sector/industry/exchange from this when the symbol wasn't
        already covered by the full directory discovery pass."""
        profile = await self._service.get_company_profile(symbol)
        return {
            "symbol": profile.symbol,
            "name": profile.name,
            "name_ar": profile.name_ar,
            "sector": profile.sector,
            "industry": profile.industry,
            "exchange": profile.exchange,
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        summary = await self._service.get_index_snapshot(index_name)
        return {
            "index_name": summary.index,
            "value": summary.value,
            "change": summary.change,
            "change_percent": summary.change_percent,
            "timestamp": (summary.timestamp or datetime.now(timezone.utc)).isoformat(),
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """AI-generated stock events via GET /events/ -- the closest
        verified endpoint; SAHMK documents no general news/headlines
        endpoint (Pro+ plan required)."""
        events = await self._service.get_recent_events(limit=limit)
        return [
            {
                "headline": event.headline,
                "symbol": event.symbol,
                "timestamp": (event.timestamp or datetime.now(timezone.utc)).isoformat(),
                "source": "sahmk",
                "is_synthetic": False,
            }
            for event in events
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


MarketDataProviderFactory.register("sahmk", SahmkMarketDataProvider)
