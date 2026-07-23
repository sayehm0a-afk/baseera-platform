"""
Market Data Provider abstraction for Saudi financial market data.

This module provides a clean abstraction layer for integrating with Saudi market data providers.
Supports authentication, reconnection, retry logic, rate limiting, health checking, and failover.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class MarketDataType(Enum):
    """Types of market data available."""
    STOCK_PRICE = "stock_price"
    INDEX_DATA = "index_data"
    MARKET_NEWS = "market_news"
    TRADING_VOLUME = "trading_volume"
    MARKET_SENTIMENT = "market_sentiment"


class ProviderHealth(Enum):
    """Health status of the provider."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class IMarketDataProvider(ABC):
    """Interface for market data providers."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the provider."""
        pass

    @abstractmethod
    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Get stock data for a symbol."""
        pass

    @abstractmethod
    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        """Get index data."""
        pass

    @abstractmethod
    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent market news."""
        pass

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check provider health."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the provider."""
        pass


class SaudiMarketDataProvider(IMarketDataProvider):
    """
    Implementation of market data provider for Saudi market.

    Supports:
    - Authentication with API credentials
    - Automatic reconnection on connection loss
    - Exponential backoff retry logic
    - Rate limiting
    - Health checking
    - Failover preparation
    """

    def __init__(
        self,
        api_endpoint: str,
        api_key: str,
        api_secret: Optional[str] = None,
        rate_limit_calls: int = 100,
        rate_limit_period: int = 60,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        """
        Initialize the Saudi market data provider.

        Args:
            api_endpoint: Base URL for the market data API
            api_key: API key for authentication
            api_secret: Optional API secret for authentication
            rate_limit_calls: Number of calls allowed per period
            rate_limit_period: Period in seconds for rate limiting
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
        """
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.api_secret = api_secret
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period
        self.max_retries = max_retries
        self.timeout = timeout

        self.session: Optional[aiohttp.ClientSession] = None
        self.authenticated = False
        self.last_health_check: Optional[datetime] = None
        self.health_status = ProviderHealth.UNHEALTHY
        self.request_count = 0
        self.request_reset_time = datetime.now() + timedelta(seconds=rate_limit_period)
        self.auth_token: Optional[str] = None

    async def authenticate(self) -> bool:
        """
        Authenticate with the market data provider.

        Returns:
            True if authentication was successful, False otherwise
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            auth_url = f"{self.api_endpoint}/auth/token"
            payload = {
                "api_key": self.api_key,
            }
            if self.api_secret:
                payload["api_secret"] = self.api_secret

            async with self.session.post(
                auth_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get("token")
                    self.authenticated = True
                    logger.info("Successfully authenticated with market data provider")
                    return True
                else:
                    logger.error(f"Authentication failed with status {response.status}")
                    self.authenticated = False
                    return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self.authenticated = False
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError),
    )
    async def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the provider API with retry logic.

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Request body data

        Returns:
            Response data as dictionary

        Raises:
            aiohttp.ClientError: If request fails after retries
        """
        if not self.authenticated:
            raise RuntimeError("Not authenticated with provider")

        # Check rate limiting
        now = datetime.now()
        if now >= self.request_reset_time:
            self.request_count = 0
            self.request_reset_time = now + timedelta(seconds=self.rate_limit_period)

        if self.request_count >= self.rate_limit_calls:
            wait_time = (self.request_reset_time - now).total_seconds()
            logger.warning(f"Rate limit reached. Waiting {wait_time} seconds.")
            await asyncio.sleep(wait_time)
            self.request_count = 0
            self.request_reset_time = datetime.now() + timedelta(
                seconds=self.rate_limit_period
            )

        url = f"{self.api_endpoint}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

        try:
            async with self.session.request(
                method,
                url,
                params=params,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                self.request_count += 1

                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    logger.warning("Authentication token expired. Re-authenticating...")
                    await self.authenticate()
                    # Retry the request with new token
                    return await self._make_request(endpoint, method, params, data)
                else:
                    logger.error(f"API request failed with status {response.status}")
                    raise aiohttp.ClientError(
                        f"API request failed with status {response.status}"
                    )

        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {endpoint}")
            raise

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get stock data for a symbol.

        Args:
            symbol: Stock symbol (e.g., "1010" for Al Rajhi Bank)

        Returns:
            Dictionary containing stock data
        """
        try:
            data = await self._make_request(
                "/stocks/data",
                params={"symbol": symbol},
            )
            logger.debug(f"Retrieved stock data for {symbol}")
            return data
        except Exception as e:
            logger.error(f"Error retrieving stock data for {symbol}: {e}")
            raise

    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        """
        Get index data.

        Args:
            index_name: Index name (e.g., "TASI" for Saudi Arabia Tadawul All Share Index)

        Returns:
            Dictionary containing index data
        """
        try:
            data = await self._make_request(
                "/indices/data",
                params={"index": index_name},
            )
            logger.debug(f"Retrieved index data for {index_name}")
            return data
        except Exception as e:
            logger.error(f"Error retrieving index data for {index_name}: {e}")
            raise

    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent market news.

        Args:
            limit: Maximum number of news items to retrieve

        Returns:
            List of news items
        """
        try:
            data = await self._make_request(
                "/news/market",
                params={"limit": limit},
            )
            news_items = data.get("news", [])
            logger.debug(f"Retrieved {len(news_items)} market news items")
            return news_items
        except Exception as e:
            logger.error(f"Error retrieving market news: {e}")
            raise

    async def health_check(self) -> ProviderHealth:
        """
        Check the health of the market data provider.

        Returns:
            ProviderHealth status
        """
        try:
            response = await self._make_request("/health")
            self.last_health_check = datetime.now()

            if response.get("status") == "healthy":
                self.health_status = ProviderHealth.HEALTHY
            elif response.get("status") == "degraded":
                self.health_status = ProviderHealth.DEGRADED
            else:
                self.health_status = ProviderHealth.UNHEALTHY

            logger.debug(f"Provider health check: {self.health_status.value}")
            return self.health_status

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.health_status = ProviderHealth.UNHEALTHY
            return self.health_status

    async def disconnect(self) -> None:
        """Disconnect from the provider and cleanup resources."""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            self.authenticated = False
            self.auth_token = None
            logger.info("Disconnected from market data provider")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

    async def __aenter__(self):
        """Context manager entry."""
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()


class MarketDataProviderFactory:
    """Factory for creating market data provider instances."""

    _providers: Dict[str, type] = {
        "saudi": SaudiMarketDataProvider,
    }

    @classmethod
    def create(
        cls,
        provider_type: str,
        api_endpoint: str,
        api_key: str,
        **kwargs,
    ) -> IMarketDataProvider:
        """
        Create a market data provider instance.

        Args:
            provider_type: Type of provider (e.g., "saudi")
            api_endpoint: API endpoint URL
            api_key: API key for authentication
            **kwargs: Additional arguments for the provider

        Returns:
            Market data provider instance

        Raises:
            ValueError: If provider type is not supported
        """
        if provider_type not in cls._providers:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        provider_class = cls._providers[provider_type]
        return provider_class(api_endpoint, api_key, **kwargs)

    @classmethod
    def register(cls, provider_type: str, provider_class: type) -> None:
        """
        Register a custom market data provider.

        Args:
            provider_type: Type identifier for the provider
            provider_class: Provider class implementing IMarketDataProvider
        """
        cls._providers[provider_type] = provider_class
