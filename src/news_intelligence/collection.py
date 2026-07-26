"""NewsCollector: the News Collection stage of the pipeline. Wraps
`IMarketDataProvider.get_market_news()` -- already implemented for real
by `SahmkMarketDataProvider` (SAHMK's `GET /events/`, Pro+ plan) and
honestly labeled synthetic by `DevMarketDataProvider` -- with a
`TTLCache`, the exact same caching class `SahmkMarketDataService`
already uses, so concurrent/rapid requests never double-hit the
underlying metered endpoint. No news vendor is queried directly here;
this module never constructs a provider itself, only consumes whichever
one `src.market_data.provider_factory.get_market_data_provider()`
selected -- multiple providers normalize to the same
`IMarketDataProvider.get_market_news()` shape by construction, so there
is exactly one normalization boundary to cross, not one per vendor.
"""

from datetime import datetime
from typing import List, Optional

from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.news_intelligence.config import get_news_fetch_cache_ttl_seconds, get_news_fetch_limit
from src.news_intelligence.types import RawNewsItem


def _parse_timestamp(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class NewsCollector:
    def __init__(self, market_provider: IMarketDataProvider, cache: Optional[TTLCache] = None):
        self._provider = market_provider
        self._cache = cache if cache is not None else TTLCache()

    async def collect(self, limit: Optional[int] = None) -> List[RawNewsItem]:
        fetch_limit = limit if limit is not None else get_news_fetch_limit()

        async def _compute() -> List[RawNewsItem]:
            items = await self._provider.get_market_news(limit=fetch_limit)
            return [
                RawNewsItem(
                    headline=item["headline"],
                    source=item.get("source") or "unknown",
                    is_synthetic=bool(item.get("is_synthetic", False)),
                    timestamp=_parse_timestamp(item.get("timestamp")),
                    symbol=item.get("symbol"),
                    raw=item,
                )
                for item in items
                if item.get("headline")
            ]

        return await self._cache.get_or_compute(
            ("market_news", fetch_limit), _compute, ttl_seconds=get_news_fetch_cache_ttl_seconds()
        )
