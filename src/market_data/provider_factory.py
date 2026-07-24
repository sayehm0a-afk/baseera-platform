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

Secure-by-default kill switch: MARKET_DATA_PROVIDER=sahmk alone is not
enough to get a live provider back. SAHMK_LIVE_DATA_ENABLED must also be
explicitly "true" (src.market_data.config.is_live_data_enabled()) -- two
separate, deliberate environment settings are required to go live, so a
single misconfigured/leftover variable can't silently start making real,
rate-limited, billable API calls.
"""

import logging

from src.market_data import config as market_data_config
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = {"dev", "sahmk"}


def get_configured_provider() -> IMarketDataProvider:
    """Constructs the provider named by MARKET_DATA_PROVIDER, reading
    all of that provider's own configuration (credentials, endpoint,
    tunables) from src.market_data.config -- callers pass nothing."""
    provider_name = market_data_config.get_configured_provider_name()

    if provider_name == "sahmk":
        if not market_data_config.is_live_data_enabled():
            logger.warning(
                "MARKET_DATA_PROVIDER='sahmk' but SAHMK_LIVE_DATA_ENABLED "
                "is not 'true' -- falling back to 'dev' (synthetic data). "
                "Set SAHMK_LIVE_DATA_ENABLED=true to actually go live."
            )
            return DevMarketDataProvider()
        return SahmkMarketDataProvider()

    if provider_name != "dev":
        logger.warning(
            "Unknown MARKET_DATA_PROVIDER='%s' -- falling back to 'dev' "
            "(synthetic data). Supported values: %s",
            provider_name,
            sorted(_SUPPORTED_PROVIDERS),
        )

    return DevMarketDataProvider()
