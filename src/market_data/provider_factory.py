"""Builds the IMarketDataProvider the running process should use,
selected entirely by the MARKET_DATA_PROVIDER environment variable
(src.market_data.config.get_configured_provider_name()) -- this is
the "connect the provider to the existing analysis pipeline" piece of
M2.13: callers (ingestion jobs, API routes) depend on this function,
never on a hardcoded provider class, so changing MARKET_DATA_PROVIDER
in the environment is the only thing needed to move from synthetic to
live data.

Defaults to "dev" (DevMarketDataProvider) whenever MARKET_DATA_PROVIDER
is unset -- a missing configuration value must never silently attempt
a live call with no real credentials behind it.
"""

import logging

from src.market_data import config as market_data_config
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.providers.sahmak_market_data_provider import SahmakMarketDataProvider

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = {"dev", "sahmak"}


def get_configured_provider() -> IMarketDataProvider:
    """Constructs the provider named by MARKET_DATA_PROVIDER, reading
    all of that provider's own configuration (credentials, endpoint,
    tunables) from src.market_data.config -- callers pass nothing."""
    provider_name = market_data_config.get_configured_provider_name()

    if provider_name == "sahmak":
        return SahmakMarketDataProvider()

    if provider_name != "dev":
        logger.warning(
            "Unknown MARKET_DATA_PROVIDER='%s' -- falling back to 'dev' "
            "(synthetic data). Supported values: %s",
            provider_name,
            sorted(_SUPPORTED_PROVIDERS),
        )

    return DevMarketDataProvider()
