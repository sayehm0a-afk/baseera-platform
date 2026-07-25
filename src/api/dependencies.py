"""FastAPI dependencies for the API layer.

The DB session dependency is NOT redefined here -- src.core.db.database
already exposes get_db() as a FastAPI-style generator dependency
(sync Session, matching every existing DB-touching module in this
codebase); routes import that directly. This module only adds the two
provider dependencies, which need to be async (provider selection
involves an awaited connectivity probe -- see
src.market_data.provider_factory).
"""

from src.market_data.fundamental_provider_factory import get_fundamental_data_provider
from src.market_data.provider_factory import get_market_data_provider
from src.market_data.providers.fundamental_data_provider import IFundamentalDataProvider
from src.market_data.providers.market_data_provider import IMarketDataProvider


async def get_market_provider() -> IMarketDataProvider:
    return await get_market_data_provider()


async def get_fundamental_provider() -> IFundamentalDataProvider:
    return await get_fundamental_data_provider()
