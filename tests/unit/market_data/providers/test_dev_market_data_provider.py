"""Unit tests for DevMarketDataProvider -- deterministic synthetic data, no network."""

from datetime import datetime, timezone

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


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_one_bar_per_day(provider):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 5, tzinfo=timezone.utc)
    bars = await provider.get_historical_ohlcv("1010", start, end)
    assert len(bars) == 5
    assert [b["timestamp"][:10] for b in bars] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
    ]
    for bar in bars:
        assert bar["symbol"] == "1010"
        assert bar["is_synthetic"] is True
        assert bar["low"] <= bar["open"] <= bar["high"]
        assert bar["low"] <= bar["close"] <= bar["high"]


@pytest.mark.asyncio
async def test_get_historical_ohlcv_single_day_range_returns_one_bar(provider):
    day = datetime(2024, 3, 1, tzinfo=timezone.utc)
    bars = await provider.get_historical_ohlcv("1010", day, day)
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_get_historical_ohlcv_agrees_with_get_stock_data_for_today(provider, monkeypatch):
    import src.market_data.providers.dev_market_data_provider as mod

    fixed_today = datetime(2024, 6, 15, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_today

    monkeypatch.setattr(mod, "datetime", _FixedDatetime)

    today_bar = await provider.get_stock_data("1010")
    history_bars = await provider.get_historical_ohlcv("1010", fixed_today, fixed_today)

    assert len(history_bars) == 1
    assert history_bars[0]["open"] == today_bar["open"]
    assert history_bars[0]["close"] == today_bar["close"]
    assert history_bars[0]["volume"] == today_bar["volume"]


@pytest.mark.asyncio
async def test_get_historical_ohlcv_is_deterministic_across_calls(provider):
    start = datetime(2024, 2, 1, tzinfo=timezone.utc)
    end = datetime(2024, 2, 3, tzinfo=timezone.utc)
    first = await provider.get_historical_ohlcv("2222", start, end)
    second = await provider.get_historical_ohlcv("2222", start, end)
    assert first == second
