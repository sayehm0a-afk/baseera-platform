"""Fundamental data provider abstraction.

Interface + factory only -- deliberately no real vendor implementation.
Mirrors IMarketDataProvider/MarketDataProviderFactory
(market_data_provider.py, M0/M1) exactly, so a future real vendor
integration (out of scope for M2.3, per the approved M2 blueprint's
"no data vendor contracted" risk item, unchanged since M2.1) has an
established pattern to follow rather than inventing a new one.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Type

logger = logging.getLogger(__name__)


class ProviderHealth(Enum):
    """Health status of the provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class IFundamentalDataProvider(ABC):
    """Interface for fundamental (financial-statement) data providers."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the provider."""

    @abstractmethod
    async def get_fundamentals(self, symbol: str, period_type: str = "annual") -> Dict[str, Any]:
        """Get the most recent financial-statement snapshot for a symbol."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check provider health."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the provider."""


class FundamentalDataProviderFactory:
    """Factory for creating fundamental data provider instances."""

    _providers: Dict[str, Type[IFundamentalDataProvider]] = {}

    @classmethod
    def create(cls, provider_type: str, **kwargs) -> IFundamentalDataProvider:
        """Create a fundamental data provider instance.

        Args:
            provider_type: Type of provider (e.g., "dev")
            **kwargs: Additional arguments for the provider

        Returns:
            Fundamental data provider instance

        Raises:
            ValueError: If provider type is not registered
        """
        if provider_type not in cls._providers:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        provider_class = cls._providers[provider_type]
        return provider_class(**kwargs)

    @classmethod
    def register(cls, provider_type: str, provider_class: Type[IFundamentalDataProvider]) -> None:
        """Register a fundamental data provider.

        Args:
            provider_type: Type identifier for the provider
            provider_class: Provider class implementing IFundamentalDataProvider
        """
        cls._providers[provider_type] = provider_class
