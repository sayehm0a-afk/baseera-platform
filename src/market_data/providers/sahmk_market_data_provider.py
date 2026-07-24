"""SAHMK (sahmk.sa) market data provider.

Every endpoint, header, and parameter used here is verified against
SAHMK's own official sources (their public Python SDK's README/
CHANGELOG on GitHub and PyPI) -- see docs/SAHMK_INTEGRATION.md for the
full source list and, just as importantly, for what could **not** be
verified and is therefore handled defensively rather than assumed.
Nothing here was guessed; anything not confirmed is flagged in that
document.

No credential is ever hardcoded: SAHMK_API_KEY/SAHMK_BASE_URL are read
lazily from src.market_data.config, never at import time, never as a
literal in this file.

Resilience is composed from two existing, already-tested building
blocks, unchanged in shape from M2.13's design:
  - src.core.runtime.reliability_layer.circuit_breaker.CircuitBreaker
    wraps every outbound call.
  - tenacity's @retry handles per-call retries *inside* each
    circuit-breaker-guarded attempt, tuned to SAHMK's own documented
    retry defaults (3 attempts, 0.5s/1s/2s backoff, honoring a
    `Retry-After` header on 429 instead of the computed delay).
Responses are cached via TTLCache, with concurrent identical requests
deduplicated to a single underlying call (TTLCache.get_or_compute).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.runtime.reliability_layer.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from src.market_data import config as market_data_config
from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.models import MarketIndex, MarketQuote
from src.market_data.providers.market_data_provider import (
    IMarketDataProvider,
    MarketDataProviderFactory,
    ProviderHealth,
)
from src.market_data.validators.symbol_validator import validate_symbol_format

logger = logging.getLogger(__name__)

_VALID_INDEX_NAMES = {"TASI", "NOMU", "NOMUC"}


class SahmkError(Exception):
    """Base class for every error this provider raises. Never carries
    the API key -- only endpoint paths and response status/bodies are
    included in messages."""


class SahmkAuthenticationError(SahmkError):
    """The configured SAHMK_API_KEY was rejected (or is unset).
    Non-retryable."""


class SahmkEntitlementError(SahmkError):
    """The key is valid but the current plan does not permit this
    endpoint (confirmed REST shape: `403` with body `PLAN_LIMIT`).
    Non-retryable."""


class SahmkResponseValidationError(SahmkError):
    """SAHMK returned a 200 whose body did not contain the fields this
    provider needs -- raised instead of silently reading `None`/missing
    keys as if they were valid data."""


class SahmkRequestError(SahmkError):
    """Any other non-2xx response not covered by the classes above."""


class _SahmkRateLimitedError(aiohttp.ClientError):
    """Internal-only: a 429 response, expressed as an aiohttp.ClientError
    subclass so tenacity's existing retry_if_exception_type(aiohttp.ClientError)
    catches it identically to a 5xx, while still carrying `retry_after`
    so the wait strategy can honor it."""

    def __init__(self, endpoint: str, retry_after: Optional[str]):
        super().__init__(f"SAHMK rate limit (429) from {endpoint}")
        self.retry_after = retry_after


_default_wait = wait_exponential(multiplier=0.5, max=2)


def _sahmk_wait(retry_state):
    """SAHMK's own documented policy: 0.5s/1s/2s exponential backoff,
    except a 429 with a `Retry-After` header uses that server-specified
    wait instead."""
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    if isinstance(exc, _SahmkRateLimitedError) and exc.retry_after:
        try:
            return float(exc.retry_after)
        except (TypeError, ValueError):
            pass
    return _default_wait(retry_state)


class SahmkMarketDataProvider(IMarketDataProvider):
    """IMarketDataProvider implementation for the SAHMK API.

    Real endpoint: https://app.sahmk.sa/api/v1 (confirmed). Wired for
    production use but not yet exercised against a real account -- no
    key has been used against a live endpoint as of this milestone (see
    docs/SAHMK_INTEGRATION.md's "Known gaps" section for what Phase 7's
    limited real-key testing needs to confirm).
    """

    def __init__(
        self,
        api_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        cache: Optional[TTLCache] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.api_endpoint = api_endpoint if api_endpoint is not None else market_data_config.get_sahmk_base_url()
        self.api_key = api_key if api_key is not None else market_data_config.get_sahmk_api_key()
        self.timeout = market_data_config.get_provider_timeout_seconds()

        self.session: Optional[aiohttp.ClientSession] = None
        self.authenticated = False
        self.health_status = ProviderHealth.UNHEALTHY

        self._cache = cache if cache is not None else TTLCache(
            default_ttl_seconds=market_data_config.get_quote_cache_ttl_seconds()
        )
        self._historical_cache_ttl = market_data_config.get_historical_cache_ttl_seconds()
        self._circuit_breaker = circuit_breaker if circuit_breaker is not None else CircuitBreaker(
            failure_threshold=market_data_config.get_circuit_breaker_failure_threshold(),
            recovery_timeout=market_data_config.get_circuit_breaker_recovery_timeout_seconds(),
        )
        # Approximate, in-process usage counter (Phase 5's "عداد داخلي
        # تقريبي لاستهلاك API") -- counts real outbound HTTP attempts,
        # including retries, not cache hits. Approximate because it
        # resets on process restart and is not shared across workers;
        # SAHMK's own account dashboard remains the source of truth.
        self.request_count = 0

    async def authenticate(self) -> bool:
        """SAHMK has no token-exchange endpoint (confirmed) -- every
        request just carries X-API-Key. This method's job is to fail
        fast with a clear signal if the key is missing or rejected, via
        one cheap, Free-tier call, rather than silently deferring that
        discovery to whatever the first real data call happens to be."""
        if not self.api_key or not self.api_endpoint:
            logger.error(
                "SahmkMarketDataProvider.authenticate(): SAHMK_API_KEY/"
                "SAHMK_BASE_URL are not configured -- cannot authenticate."
            )
            self.authenticated = False
            return False

        try:
            await self._request("/market/summary/", params={"index": "TASI"})
            self.authenticated = True
            return True
        except SahmkAuthenticationError:
            self.authenticated = False
            return False
        except SahmkEntitlementError:
            # The key itself worked; only this specific call was
            # plan-gated (shouldn't happen for a Free-tier endpoint, but
            # if it does, the key is still valid).
            self.authenticated = True
            return True
        except CircuitBreakerOpenError:
            logger.error("SAHMK authentication skipped: circuit breaker is OPEN")
            self.authenticated = False
            return False
        except Exception as e:
            logger.error(f"SAHMK authentication error: {e}")
            self.authenticated = False
            return False

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=_sahmk_wait,
        retry=retry_if_exception_type(aiohttp.ClientError),
    )
    async def _retrying_call(func):
        return await func()

    async def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise SahmkAuthenticationError("SAHMK_API_KEY is not configured")

        async def _do_request() -> Dict[str, Any]:
            if not self.session:
                self.session = aiohttp.ClientSession()
            self.request_count += 1
            headers = {"X-API-Key": self.api_key}
            async with self.session.get(
                f"{self.api_endpoint}{endpoint}",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status == 200:
                    try:
                        return await response.json()
                    except Exception as exc:
                        raise SahmkResponseValidationError(
                            f"Non-JSON 200 response from {endpoint}"
                        ) from exc
                if response.status == 401:
                    raise SahmkAuthenticationError(
                        f"SAHMK rejected the configured API key (endpoint: {endpoint})"
                    )
                if response.status == 403:
                    raise SahmkEntitlementError(
                        f"SAHMK plan does not permit '{endpoint}' (403 PLAN_LIMIT)"
                    )
                if response.status == 429:
                    raise _SahmkRateLimitedError(endpoint, response.headers.get("Retry-After"))
                if 500 <= response.status < 600:
                    # aiohttp.ClientError -> retried by _retrying_call
                    raise aiohttp.ClientError(f"SAHMK server error {response.status} from {endpoint}")
                raise SahmkRequestError(f"Unexpected status {response.status} from {endpoint}")

        return await self._circuit_breaker.execute(self._retrying_call, _do_request)

    @staticmethod
    def _require_fields(payload: Dict[str, Any], fields: List[str], context: str) -> None:
        missing = [f for f in fields if f not in payload]
        if missing:
            raise SahmkResponseValidationError(
                f"{context}: response missing expected field(s) {missing}"
            )

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Returns today's OHLCV bar via /historical/ (see
        docs/SAHMK_INTEGRATION.md for why this does not use /quote/)."""
        validate_symbol_format(symbol)
        today = datetime.now(timezone.utc)

        async def _fetch() -> Dict[str, Any]:
            bars = await self._fetch_historical_bars(symbol, today, today)
            if not bars:
                raise SahmkResponseValidationError(
                    f"No OHLCV bar returned for '{symbol}' on {today.date().isoformat()}"
                )
            return bars[-1]

        return await self._cache.get_or_compute(
            ("quote", symbol),
            _fetch,
            ttl_seconds=market_data_config.get_quote_cache_ttl_seconds(),
        )

    async def get_historical_ohlcv(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[Dict[str, Any]]:
        validate_symbol_format(symbol)
        return await self._cache.get_or_compute(
            ("history", symbol, start.date().isoformat(), end.date().isoformat()),
            lambda: self._fetch_historical_bars(symbol, start, end),
            ttl_seconds=self._historical_cache_ttl,
        )

    async def _fetch_historical_bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[Dict[str, Any]]:
        # Date-only wire format (YYYY-MM-DD): UNVERIFIED, see
        # docs/SAHMK_INTEGRATION.md's "Known gaps" -- most defensible
        # reading for a daily-interval endpoint, not a confirmed fact.
        data = await self._request(
            f"/historical/{symbol}/",
            params={
                "interval": "1d",
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
            },
        )
        bars = data.get("bars", data.get("results", []))
        normalized: List[Dict[str, Any]] = []
        for bar in bars:
            self._require_fields(
                bar, ["open", "high", "low", "close", "volume", "timestamp"],
                f"/historical/{symbol}/ bar",
            )
            normalized.append(
                {
                    "symbol": symbol,
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "volume": bar["volume"],
                    "timestamp": bar["timestamp"],
                }
            )
        return normalized

    async def get_latest_quote(self, symbol: str) -> MarketQuote:
        """Not part of IMarketDataProvider -- SAHMK-specific extension
        for callers that want a live price/change reading (Free tier)
        and don't need a full OHLCV bar. See docs/SAHMK_INTEGRATION.md."""
        validate_symbol_format(symbol)

        async def _fetch() -> MarketQuote:
            data = await self._request(f"/quote/{symbol}/")
            self._require_fields(
                data, ["symbol", "price", "change", "change_percent", "volume"],
                f"/quote/{symbol}/",
            )
            return MarketQuote(
                symbol=data["symbol"],
                price=data["price"],
                change=data["change"],
                change_percent=data["change_percent"],
                volume=data["volume"],
                value=data.get("value"),
                name_en=data.get("name_en"),
                name_ar=data.get("name_ar"),
                timestamp=datetime.now(timezone.utc),
                source="sahmk",
            )

        return await self._cache.get_or_compute(
            ("latest_quote", symbol),
            _fetch,
            ttl_seconds=market_data_config.get_quote_cache_ttl_seconds(),
        )

    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        if index_name not in _VALID_INDEX_NAMES:
            raise SahmkResponseValidationError(
                f"'{index_name}' is not a SAHMK-documented index; expected one of {sorted(_VALID_INDEX_NAMES)}"
            )

        async def _fetch() -> Dict[str, Any]:
            data = await self._request("/market/summary/", params={"index": index_name})
            self._require_fields(data, ["index_value", "index_change_percent"], "/market/summary/")
            index = MarketIndex(
                index_name=index_name,
                value=data["index_value"],
                change=data.get("index_change", 0.0),
                change_percent=data["index_change_percent"],
                is_delayed=data.get("is_delayed"),
                timestamp=datetime.now(timezone.utc),
                source="sahmk",
            )
            return {
                "index_name": index.index_name,
                "value": index.value,
                "change": index.change,
                "change_percent": index.change_percent,
                "is_delayed": index.is_delayed,
                "timestamp": index.timestamp.isoformat(),
                "source": index.source,
            }

        return await self._cache.get_or_compute(
            ("index", index_name),
            _fetch,
            ttl_seconds=market_data_config.get_quote_cache_ttl_seconds(),
        )

    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Maps to /events/ (Pro+, "AI-generated stock events") -- the
        closest verified endpoint; SAHMK does not document a general
        news/headlines endpoint. A Free/Starter account will see this
        raise SahmkEntitlementError, surfaced as-is, not swallowed."""
        data = await self._request("/events/", params={"limit": limit})
        return data.get("events", data.get("results", []))

    async def health_check(self) -> ProviderHealth:
        try:
            await self._request("/market/summary/", params={"index": "TASI"})
            self.health_status = ProviderHealth.HEALTHY
        except SahmkAuthenticationError:
            self.health_status = ProviderHealth.UNHEALTHY
        except Exception as e:
            logger.error(f"SAHMK health check failed: {e}")
            self.health_status = ProviderHealth.DEGRADED
        return self.health_status

    async def disconnect(self) -> None:
        try:
            if self.session:
                await self.session.close()
                self.session = None
            self.authenticated = False
            logger.info("Disconnected from SAHMK market data provider")
        except Exception as e:
            logger.error(f"Error during SAHMK disconnect: {e}")


MarketDataProviderFactory.register("sahmk", SahmkMarketDataProvider)
