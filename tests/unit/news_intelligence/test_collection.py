"""Unit tests for src.news_intelligence.collection.NewsCollector --
mocked IMarketDataProvider, no real network."""

import pytest

from src.market_data.caching.ttl_cache import TTLCache
from src.news_intelligence.collection import NewsCollector
from src.news_intelligence.config import get_news_fetch_limit


class _FakeProvider:
    def __init__(self, items=None):
        self.items = items if items is not None else []
        self.call_count = 0

    async def get_market_news(self, limit=10):
        self.call_count += 1
        return self.items


@pytest.mark.asyncio
async def test_collect_normalizes_provider_items():
    provider = _FakeProvider(
        items=[
            {"headline": "Aramco reports profit", "symbol": "2222", "timestamp": "2026-01-01T00:00:00+00:00", "source": "sahmk", "is_synthetic": False},
        ]
    )
    collector = NewsCollector(market_provider=provider)
    items = await collector.collect()
    assert len(items) == 1
    assert items[0].headline == "Aramco reports profit"
    assert items[0].symbol == "2222"
    assert items[0].source == "sahmk"
    assert items[0].is_synthetic is False
    assert items[0].timestamp is not None


@pytest.mark.asyncio
async def test_collect_skips_items_without_a_headline():
    provider = _FakeProvider(items=[{"symbol": "2222", "source": "sahmk"}, {"headline": "Real story", "source": "sahmk"}])
    collector = NewsCollector(market_provider=provider)
    items = await collector.collect()
    assert len(items) == 1
    assert items[0].headline == "Real story"


@pytest.mark.asyncio
async def test_collect_defaults_source_and_is_synthetic_when_missing():
    provider = _FakeProvider(items=[{"headline": "Untagged story"}])
    collector = NewsCollector(market_provider=provider)
    items = await collector.collect()
    assert items[0].source == "unknown"
    assert items[0].is_synthetic is False


@pytest.mark.asyncio
async def test_collect_uses_the_configured_default_limit():
    provider = _FakeProvider(items=[])

    async def _spy_get_market_news(limit=10):
        provider.call_count += 1
        provider.last_limit = limit
        return []

    provider.get_market_news = _spy_get_market_news
    collector = NewsCollector(market_provider=provider)
    await collector.collect()
    assert provider.last_limit == get_news_fetch_limit()


@pytest.mark.asyncio
async def test_collect_respects_an_explicit_limit():
    provider = _FakeProvider(items=[])

    async def _spy_get_market_news(limit=10):
        provider.last_limit = limit
        return []

    provider.get_market_news = _spy_get_market_news
    collector = NewsCollector(market_provider=provider)
    await collector.collect(limit=5)
    assert provider.last_limit == 5


@pytest.mark.asyncio
async def test_collect_reuses_a_cached_result_within_the_ttl():
    provider = _FakeProvider(items=[{"headline": "Cached story", "source": "sahmk"}])
    collector = NewsCollector(market_provider=provider, cache=TTLCache(default_ttl_seconds=60.0))

    await collector.collect(limit=10)
    await collector.collect(limit=10)

    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_collect_does_not_share_a_cache_key_across_different_limits():
    provider = _FakeProvider(items=[{"headline": "Story", "source": "sahmk"}])
    collector = NewsCollector(market_provider=provider, cache=TTLCache(default_ttl_seconds=60.0))

    await collector.collect(limit=10)
    await collector.collect(limit=20)

    assert provider.call_count == 2
