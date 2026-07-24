"""Unit tests for SaudiMarketDataProvider.get_historical_ohlcv (M2.13).

No live endpoint is called: `_make_request` (already tenacity-retried,
rate-limited, auth-refreshing -- unchanged, existing behavior) is
mocked directly, matching this codebase's established pattern of
mocking at a class's own already-tested internal boundary rather than
reaching into aiohttp internals.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.market_data.providers.market_data_provider import (
    MarketDataProviderFactory,
    SaudiMarketDataProvider,
)


@pytest.fixture
def provider():
    return SaudiMarketDataProvider(api_endpoint="https://example.invalid", api_key="k")


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_bars_from_response(provider):
    provider._make_request = AsyncMock(
        return_value={
            "bars": [
                {"symbol": "1010", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100,
                 "timestamp": "2024-01-01T00:00:00+00:00"},
            ]
        }
    )
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    bars = await provider.get_historical_ohlcv("1010", start, end)

    assert len(bars) == 1
    assert bars[0]["symbol"] == "1010"
    provider._make_request.assert_awaited_once_with(
        "/stocks/history",
        params={"symbol": "1010", "start": start.isoformat(), "end": end.isoformat()},
    )


@pytest.mark.asyncio
async def test_get_historical_ohlcv_returns_empty_list_when_no_bars_key(provider):
    provider._make_request = AsyncMock(return_value={})
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    bars = await provider.get_historical_ohlcv("1010", start, end)

    assert bars == []


@pytest.mark.asyncio
async def test_get_historical_ohlcv_propagates_request_errors(provider):
    provider._make_request = AsyncMock(side_effect=RuntimeError("boom"))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError, match="boom"):
        await provider.get_historical_ohlcv("1010", start, end)


def test_saudi_provider_is_registered_with_factory():
    provider = MarketDataProviderFactory.create("saudi", "https://example.invalid", "k")
    assert isinstance(provider, SaudiMarketDataProvider)
