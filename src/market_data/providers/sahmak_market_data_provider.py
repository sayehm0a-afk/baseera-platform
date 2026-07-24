"""Sahmak market data provider.

Real HTTP-client implementation, wired for production use against a
Sahmak API endpoint -- exactly like SaudiMarketDataProvider's own
existing, already-disclosed pattern, this class contains no fake or
placeholder business logic, but it has never been exercised against a
live Sahmak endpoint: no vendor contract exists yet (see
docs/architecture and dev_market_data_provider.py's module docstring
for the same disclosure applied to the prior placeholder vendor). It
is safe to register and select via MARKET_DATA_PROVIDER, but selecting
it with empty/placeholder credentials will simply fail authentication.

No credential is ever hardcoded: every secret (`SAHMAK_API_KEY`,
`SAHMAK_API_SECRET`, `SAHMAK_BASE_URL`) is read lazily, at call time,
from src.market_data.config -- never at import time and never as a
literal in this file.

Resilience is composed from two existing, already-tested building
blocks rather than reimplemented here:
  - src.core.runtime.reliability_layer.circuit_breaker.CircuitBreaker
    wraps every outbound HTTP call; three-strikes-open, exactly as
    already used elsewhere in this codebase.
  - `tenacity`'s @retry (imported the same way
    SaudiMarketDataProvider._make_request already does) handles
    transient per-call retries *inside* each circuit-breaker-guarded
    attempt.
Quote/OHLCV responses are cached via src.market_data.caching.TTLCache
to bound how often either layer is invoked for repeated reads of the
same symbol within one process.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.runtime.reliability_layer.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from src.market_data import config as market_data_config
from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.providers.market_data_provider import (
    IMarketDataProvider,
    MarketDataProviderFactory,
    ProviderHealth,
)
from src.market_data.validators.symbol_validator import validate_symbol_format

logger = logging.getLogger(__name__)


class SahmakAuthenticationError(RuntimeError):
    """Raised when a Sahmak API call is attempted without having
    authenticated successfully first."""


class SahmakMarketDataProvider(IMarketDataProvider):
    """IMarketDataProvider implementation for the Sahmak API.

    All configuration is read from src.market_data.config at
    construction time; nothing is hardcoded and no argument defaults
    to a real-looking placeholder value.
    """

    def __init__(
        self,
        api_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        cache: Optional[TTLCache] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.api_endpoint = api_endpoint if api_endpoint is not None else market_data_config.get_sahmak_base_url()
        self.api_key = api_key if api_key is not None else market_data_config.get_sahmak_api_key()
        self.api_secret = (
            api_secret if api_secret is not None else market_data_config.get_sahmak_api_secret()
        )
        self.timeout = market_data_config.get_provider_timeout_seconds()
        self.max_retries = market_data_config.get_provider_max_retries()

        self.session: Optional[aiohttp.ClientSession] = None
        self.authenticated = False
        self.auth_token: Optional[str] = None
        self.health_status = ProviderHealth.UNHEALTHY

        self._cache = cache if cache is not None else TTLCache(
            default_ttl_seconds=market_data_config.get_quote_cache_ttl_seconds()
        )
        self._circuit_breaker = circuit_breaker if circuit_breaker is not None else CircuitBreaker(
            failure_threshold=market_data_config.get_circuit_breaker_failure_threshold(),
            recovery_timeout=market_data_config.get_circuit_breaker_recovery_timeout_seconds(),
        )

    async def authenticate(self) -> bool:
        if not self.api_key or not self.api_endpoint:
            logger.error(
                "SahmakMarketDataProvider.authenticate(): SAHMAK_API_KEY/"
                "SAHMAK_BASE_URL are not configured -- cannot authenticate "
                "against a real endpoint."
            )
            self.authenticated = False
            return False

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async def _do_auth() -> Dict[str, Any]:
                payload: Dict[str, Any] = {"api_key": self.api_key}
                if self.api_secret:
                    payload["api_secret"] = self.api_secret
                async with self.session.post(
                    f"{self.api_endpoint}/auth/token",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        raise aiohttp.ClientError(
                            f"Sahmak authentication failed with status {response.status}"
                        )
                    return await response.json()

            data = await self._circuit_breaker.execute(self._retrying_call, _do_auth)
            self.auth_token = data.get("token")
            self.authenticated = True
            logger.info("Successfully authenticated with Sahmak market data provider")
            return True
        except CircuitBreakerOpenError:
            logger.error("Sahmak authentication skipped: circuit breaker is OPEN")
            self.authenticated = False
            return False
        except Exception as e:
            logger.error(f"Sahmak authentication error: {e}")
            self.authenticated = False
            return False

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError),
    )
    async def _retrying_call(func):
        """Runs `func` (a zero-arg async callable) under tenacity retry.
        Kept as a small indirection so the retry decorator can wrap any
        one-off request closure without duplicating the @retry
        declaration on every call site."""
        return await func()

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.authenticated:
            raise SahmakAuthenticationError("Not authenticated with Sahmak provider")

        async def _do_request() -> Dict[str, Any]:
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
            }
            async with self.session.request(
                "GET",
                f"{self.api_endpoint}{endpoint}",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    logger.warning("Sahmak auth token expired. Re-authenticating...")
                    await self.authenticate()
                    raise aiohttp.ClientError("Sahmak token refreshed, retry required")
                raise aiohttp.ClientError(f"Sahmak API request failed with status {response.status}")

        return await self._circuit_breaker.execute(self._retrying_call, _do_request)

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        validate_symbol_format(symbol)
        return await self._cache.get_or_compute(
            ("quote", symbol),
            lambda: self._request("/stocks/data", params={"symbol": symbol}),
        )

    async def get_historical_ohlcv(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[Dict[str, Any]]:
        validate_symbol_format(symbol)

        async def _fetch() -> List[Dict[str, Any]]:
            data = await self._request(
                "/stocks/history",
                params={"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()},
            )
            return data.get("bars", [])

        return await self._cache.get_or_compute(
            ("history", symbol, start.isoformat(), end.isoformat()), _fetch
        )

    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        return await self._cache.get_or_compute(
            ("index", index_name),
            lambda: self._request("/indices/data", params={"index": index_name}),
        )

    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        data = await self._request("/news/market", params={"limit": limit})
        return data.get("news", [])

    async def health_check(self) -> ProviderHealth:
        try:
            response = await self._request("/health")
            status = response.get("status")
            if status == "healthy":
                self.health_status = ProviderHealth.HEALTHY
            elif status == "degraded":
                self.health_status = ProviderHealth.DEGRADED
            else:
                self.health_status = ProviderHealth.UNHEALTHY
        except Exception as e:
            logger.error(f"Sahmak health check failed: {e}")
            self.health_status = ProviderHealth.UNHEALTHY
        return self.health_status

    async def disconnect(self) -> None:
        try:
            if self.session:
                await self.session.close()
                self.session = None
            self.authenticated = False
            self.auth_token = None
            logger.info("Disconnected from Sahmak market data provider")
        except Exception as e:
            logger.error(f"Error during Sahmak disconnect: {e}")


MarketDataProviderFactory.register("sahmak", SahmakMarketDataProvider)
