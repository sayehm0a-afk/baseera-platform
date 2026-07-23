"""Unit tests for DevMarketDataProvider -- deterministic synthetic data, no network."""

import pytest

from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.market_data_provider import (
    MarketDataProviderFactory,
    ProviderHealth,
)


@pytest.fixture
def provider():
    return DevMarketDataProvider()


@pytest.mark.asyncio
async def test_authenticate_always_succeeds(provider):
    assert await provider.authenticate() is True


@pytest.mark.asyncio
async def test_get_stock_data_is_labeled_synthetic(provider):
    data = await provider.get_stock_data("1010")
    assert data["symbol"] == "1010"
    assert data["source"] == "dev-synthetic"
    assert data["is_synthetic"] is True
    assert data["low"] <= data["open"] <= data["high"]
    assert data["low"] <= data["close"] <= data["high"]
    assert data["volume"] >= 0


@pytest.mark.asyncio
async def test_get_stock_data_is_deterministic_for_same_symbol_and_day(provider):
    first = await provider.get_stock_data("1010")
    second = await provider.get_stock_data("1010")
    assert first["open"] == second["open"]
    assert first["close"] == second["close"]
    assert first["volume"] == second["volume"]


@pytest.mark.asyncio
async def test_get_stock_data_differs_across_symbols(provider):
    a = await provider.get_stock_data("1010")
    b = await provider.get_stock_data("2222")
    assert a["open"] != b["open"]


@pytest.mark.asyncio
async def test_get_index_data_is_labeled_synthetic(provider):
    data = await provider.get_index_data("TASI")
    assert data["index_name"] == "TASI"
    assert data["source"] == "dev-synthetic"
    assert data["is_synthetic"] is True
    assert "value" in data
    assert "change_percent" in data


@pytest.mark.asyncio
async def test_get_market_news_respects_limit(provider):
    news = await provider.get_market_news(limit=3)
    assert len(news) == 3
    for item in news:
        assert item["is_synthetic"] is True
        assert item["source"] == "dev-synthetic"


@pytest.mark.asyncio
async def test_health_check_reflects_authentication_state(provider):
    assert await provider.health_check() == ProviderHealth.UNHEALTHY
    await provider.authenticate()
    assert await provider.health_check() == ProviderHealth.HEALTHY
    await provider.disconnect()
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


def test_provider_is_registered_with_factory():
    provider = MarketDataProviderFactory.create("dev", "dev://synthetic", "dev")
    assert isinstance(provider, DevMarketDataProvider)
