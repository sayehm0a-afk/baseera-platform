"""Market data provider module."""

# Fixed in M2.1: this re-export pointed at .market_data_provider, the
# pre-M1 location. M1 moved the file to .providers.market_data_provider
# and updated every other reference, but this __init__.py had zero real
# importers at the time (see docs/architecture/runtime-ownership.md), so
# the broken import went uncaught until M2.1 became the first real
# importer of this package.
from .providers.market_data_provider import (
    IMarketDataProvider,
    MarketDataType,
    ProviderHealth,
    SaudiMarketDataProvider,
    MarketDataProviderFactory,
)
from .providers.dev_market_data_provider import DevMarketDataProvider

__all__ = [
    "IMarketDataProvider",
    "MarketDataType",
    "ProviderHealth",
    "SaudiMarketDataProvider",
    "MarketDataProviderFactory",
    "DevMarketDataProvider",
]
