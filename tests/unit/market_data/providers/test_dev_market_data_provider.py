"""Unit tests for DevMarketDataProvider -- deterministic synthetic data, no network."""

from datetime import date

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


# --- get_historical_ohlcv() -----------------------------------------------


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_one_bar_per_day(provider):
    bars = await provider.get_historical_ohlcv("1010", date(2026, 1, 1), date(2026, 1, 5))
    assert len(bars) == 5
    timestamps = [b["timestamp"] for b in bars]
    assert timestamps == sorted(timestamps)
    for bar in bars:
        assert bar["source"] == "dev-synthetic"
        assert bar["is_synthetic"] is True
        assert bar["low"] <= bar["open"] <= bar["high"]
        assert bar["low"] <= bar["close"] <= bar["high"]


@pytest.mark.asyncio
async def test_get_historical_ohlcv_matches_get_stock_data_for_today(provider):
    """Both must agree on today's bar -- one shared code path, not two
    independent seeded generators that could silently drift apart."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    single = await provider.get_stock_data("1010")
    ranged = await provider.get_historical_ohlcv("1010", today, today)
    assert len(ranged) == 1
    assert ranged[0] == single


@pytest.mark.asyncio
async def test_get_historical_ohlcv_is_deterministic(provider):
    first = await provider.get_historical_ohlcv("1010", date(2026, 1, 1), date(2026, 1, 3))
    second = await provider.get_historical_ohlcv("1010", date(2026, 1, 1), date(2026, 1, 3))
    assert first == second


@pytest.mark.asyncio
async def test_get_historical_ohlcv_empty_when_start_after_end(provider):
    bars = await provider.get_historical_ohlcv("1010", date(2026, 1, 5), date(2026, 1, 1))
    assert bars == []


@pytest.mark.asyncio
async def test_get_historical_ohlcv_rejects_non_daily_interval(provider):
    with pytest.raises(ValueError):
        await provider.get_historical_ohlcv("1010", date(2026, 1, 1), date(2026, 1, 2), interval="1h")
