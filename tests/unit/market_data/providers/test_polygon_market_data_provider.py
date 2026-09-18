"""Unit tests for PolygonMarketDataProvider -- the IMarketDataProvider
adapter. PolygonMarketDataService is replaced with an AsyncMock so no
network call is ever made; assertions focus on the adapter's own
mapping/error-translation logic (already covered independently by
test_client.py and test_service.py). Mirrors
tests/unit/market_data/providers/test_sahmk_market_data_provider.py's
style and coverage depth."""

import os
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.providers.market_data_provider import MarketDataProviderFactory, ProviderHealth
from src.market_data.providers.polygon_market_data_provider import PolygonMarketDataProvider
from src.market_data.polygon.exceptions import (
    PolygonAuthenticationError,
    PolygonConfigurationError,
)
from src.market_data.polygon.models import (
    PolygonBar,
    PolygonMarketStatus,
    PolygonNewsItem,
    PolygonTickerDetails,
)


def _provider_with_mock_service():
    provider = PolygonMarketDataProvider(api_endpoint="https://polygon.example.invalid", api_key="key")
    provider._service = AsyncMock()
    provider._service.has_credentials = True
    return provider


# --- construction: never crashes, never dials out, even with no key --------


def test_construction_with_no_api_key_does_not_raise(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    provider = PolygonMarketDataProvider()
    assert provider.is_synthetic is False
    assert provider.authenticated is False


def test_construction_with_no_env_vars_at_all_does_not_raise():
    """The exact scenario the task's own manual smoke-check runs:
    `PolygonMarketDataProvider()` with zero env vars configured must
    never crash or attempt a network call at construction time."""
    env_backup = dict(os.environ)
    for key in list(os.environ):
        if key.startswith("POLYGON_"):
            del os.environ[key]
    try:
        provider = PolygonMarketDataProvider()
        assert provider.api_key is None
    finally:
        os.environ.clear()
        os.environ.update(env_backup)


# --- authenticate() -----------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_fails_fast_without_credentials():
    provider = PolygonMarketDataProvider(api_endpoint="x", api_key="")
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_succeeds_on_valid_key():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.return_value = PolygonMarketStatus(
        market="open", server_time=None, exchanges={}, raw={}
    )
    result = await provider.authenticate()
    assert result is True
    assert provider.authenticated is True
    provider._service.get_market_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_rejected_key():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.side_effect = PolygonAuthenticationError("bad key")
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_configuration_error():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.side_effect = PolygonConfigurationError("no key")
    result = await provider.authenticate()
    assert result is False


@pytest.mark.asyncio
async def test_authenticate_returns_false_when_circuit_breaker_open():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.side_effect = CircuitBreakerOpenError()
    result = await provider.authenticate()
    assert result is False


# --- check_connectivity() -------------------------------------------------


@pytest.mark.asyncio
async def test_check_connectivity_succeeds_on_valid_key():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.return_value = PolygonMarketStatus(
        market="open", server_time=None, exchanges={}, raw={}
    )
    result = await provider.check_connectivity()
    assert result is True


@pytest.mark.asyncio
async def test_check_connectivity_raises_on_rejected_key():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.side_effect = PolygonAuthenticationError("bad key")
    with pytest.raises(PolygonAuthenticationError):
        await provider.check_connectivity()


@pytest.mark.asyncio
async def test_check_connectivity_raises_when_circuit_breaker_open():
    provider = _provider_with_mock_service()
    provider._service.get_market_status.side_effect = CircuitBreakerOpenError()
    with pytest.raises(CircuitBreakerOpenError):
        await provider.check_connectivity()


# --- get_stock_data() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_stock_data_maps_bar_to_ohlcv_dict():
    provider = _provider_with_mock_service()
    provider._service.get_daily_bar.return_value = PolygonBar(
        ticker="AAPL",
        open=148.0,
        high=151.0,
        low=147.5,
        close=150.0,
        volume=1000000.0,
        timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
        vwap=149.0,
        transactions=1000,
        raw={},
    )
    data = await provider.get_stock_data("AAPL")
    assert data == {
        "symbol": "AAPL",
        "open": 148.0,
        "high": 151.0,
        "low": 147.5,
        "close": 150.0,
        "volume": 1000000.0,
        "timestamp": "2026-01-05T00:00:00+00:00",
        "source": "polygon",
        "is_synthetic": False,
    }


# --- get_historical_ohlcv() -----------------------------------------------


@pytest.mark.asyncio
async def test_get_historical_ohlcv_maps_every_bar():
    provider = _provider_with_mock_service()
    provider._service.get_aggregates.return_value = [
        PolygonBar("AAPL", 148.0, 151.0, 147.5, 150.0, 1000000.0, datetime(2026, 1, 5, tzinfo=timezone.utc), None, None, {}),
        PolygonBar("AAPL", 150.0, 153.0, 149.0, 152.0, 1200000.0, datetime(2026, 1, 6, tzinfo=timezone.utc), None, None, {}),
    ]

    bars = await provider.get_historical_ohlcv("AAPL", date(2026, 1, 5), date(2026, 1, 6))

    assert bars == [
        {
            "symbol": "AAPL", "open": 148.0, "high": 151.0, "low": 147.5, "close": 150.0,
            "volume": 1000000.0, "timestamp": "2026-01-05T00:00:00+00:00",
            "source": "polygon", "is_synthetic": False,
        },
        {
            "symbol": "AAPL", "open": 150.0, "high": 153.0, "low": 149.0, "close": 152.0,
            "volume": 1200000.0, "timestamp": "2026-01-06T00:00:00+00:00",
            "source": "polygon", "is_synthetic": False,
        },
    ]
    provider._service.get_aggregates.assert_awaited_once_with(
        "AAPL", date(2026, 1, 5), date(2026, 1, 6), multiplier=1, timespan="day"
    )


@pytest.mark.asyncio
async def test_get_historical_ohlcv_empty_list_when_no_bars():
    provider = _provider_with_mock_service()
    provider._service.get_aggregates.return_value = []
    bars = await provider.get_historical_ohlcv("AAPL", date(2026, 1, 5), date(2026, 1, 6))
    assert bars == []


@pytest.mark.asyncio
async def test_get_historical_ohlcv_maps_interval_to_polygon_timespan():
    provider = _provider_with_mock_service()
    provider._service.get_aggregates.return_value = []
    await provider.get_historical_ohlcv("AAPL", date(2026, 1, 5), date(2026, 1, 6), interval="1h")
    provider._service.get_aggregates.assert_awaited_once_with(
        "AAPL", date(2026, 1, 5), date(2026, 1, 6), multiplier=1, timespan="hour"
    )


@pytest.mark.asyncio
async def test_get_historical_ohlcv_rejects_unsupported_interval():
    provider = _provider_with_mock_service()
    with pytest.raises(ValueError):
        await provider.get_historical_ohlcv("AAPL", date(2026, 1, 5), date(2026, 1, 6), interval="7m")


# --- get_latest_quote() (extra, not part of IMarketDataProvider) ---------


@pytest.mark.asyncio
async def test_get_latest_quote_maps_bar_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_previous_close.return_value = PolygonBar(
        "AAPL", 148.0, 151.0, 147.5, 150.0, 1000000.0, datetime(2026, 1, 5, tzinfo=timezone.utc), None, None, {}
    )
    data = await provider.get_latest_quote("AAPL")
    assert data["price"] == 150.0
    assert data["source"] == "polygon"
    assert data["is_synthetic"] is False


# --- get_ticker_details() (extra, not part of IMarketDataProvider) -------


@pytest.mark.asyncio
async def test_get_ticker_details_maps_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_ticker_details.return_value = PolygonTickerDetails(
        ticker="AAPL", name="Apple Inc.", market="stocks", locale="us", primary_exchange="XNAS",
        type="CS", active=True, currency_name="usd", market_cap=3_000_000_000_000.0,
        description="Apple designs...", raw={},
    )
    profile = await provider.get_ticker_details("AAPL")
    assert profile == {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "market": "stocks",
        "primary_exchange": "XNAS",
        "type": "CS",
        "active": True,
        "currency_name": "usd",
        "market_cap": 3_000_000_000_000.0,
        "source": "polygon",
        "is_synthetic": False,
    }


# --- get_symbol_directory() (extra, not part of IMarketDataProvider) ------


@pytest.mark.asyncio
async def test_get_symbol_directory_maps_tickers_to_dicts():
    provider = _provider_with_mock_service()
    provider._service.get_ticker_directory.return_value = [
        PolygonTickerDetails(
            ticker="AAPL", name="Apple Inc.", market="stocks", locale="us", primary_exchange="XNAS",
            type="CS", active=True, currency_name="usd", market_cap=None, description=None, raw={},
        ),
    ]
    directory = await provider.get_symbol_directory()
    assert directory == [
        {
            "symbol": "AAPL", "name": "Apple Inc.", "market": "stocks", "primary_exchange": "XNAS",
            "type": "CS", "active": True, "source": "polygon", "is_synthetic": False,
        }
    ]


# --- get_index_data() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_data_maps_previous_close_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_previous_close.return_value = PolygonBar(
        "SPY", 470.0, 475.0, 469.0, 474.0, 50000000.0, datetime(2026, 1, 5, tzinfo=timezone.utc), None, None, {}
    )
    data = await provider.get_index_data("SPY")
    assert data["index_name"] == "SPY"
    assert data["value"] == 474.0
    assert data["source"] == "polygon"
    assert data["is_synthetic"] is False


# --- get_market_news() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_news_maps_news_items_to_dicts():
    provider = _provider_with_mock_service()
    provider._service.get_ticker_news.return_value = [
        PolygonNewsItem(
            id="abc", title="Headline", tickers=["AAPL"],
            published_utc=datetime(2026, 1, 5, tzinfo=timezone.utc),
            article_url="https://example.invalid/a", publisher_name="Reuters", raw={},
        )
    ]
    news = await provider.get_market_news(limit=1)
    assert news == [
        {
            "headline": "Headline",
            "symbol": "AAPL",
            "timestamp": "2026-01-05T00:00:00+00:00",
            "source": "polygon",
            "is_synthetic": False,
        }
    ]
    provider._service.get_ticker_news.assert_awaited_once_with(limit=1)


@pytest.mark.asyncio
async def test_get_market_news_handles_item_with_no_tickers():
    provider = _provider_with_mock_service()
    provider._service.get_ticker_news.return_value = [
        PolygonNewsItem(
            id="abc", title="Headline", tickers=[], published_utc=None,
            article_url=None, publisher_name=None, raw={},
        )
    ]
    news = await provider.get_market_news()
    assert news[0]["symbol"] is None


# --- health_check() -----------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_unhealthy_without_credentials():
    provider = PolygonMarketDataProvider(api_endpoint="x", api_key="")
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


@pytest.mark.asyncio
async def test_health_check_healthy_when_service_reports_healthy():
    provider = _provider_with_mock_service()
    provider._service.check_health.return_value = True
    assert await provider.health_check() == ProviderHealth.HEALTHY


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_service_reports_unhealthy():
    provider = _provider_with_mock_service()
    provider._service.check_health.return_value = False
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


@pytest.mark.asyncio
async def test_health_check_unhealthy_on_circuit_breaker_open():
    provider = _provider_with_mock_service()
    provider._service.check_health.side_effect = CircuitBreakerOpenError()
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


# --- disconnect() -----------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_closes_service_and_resets_authenticated():
    provider = _provider_with_mock_service()
    provider.authenticated = True
    await provider.disconnect()
    provider._service.close.assert_awaited_once()
    assert provider.authenticated is False


# --- factory registration --------------------------------------------------


def test_provider_is_registered_with_factory():
    provider = MarketDataProviderFactory.create("polygon", "https://polygon.example.invalid", "key")
    assert isinstance(provider, PolygonMarketDataProvider)


def test_provider_is_marked_non_synthetic():
    assert PolygonMarketDataProvider.is_synthetic is False


def test_sahmk_provider_selection_is_unaffected_by_polygon_registration():
    """Zero-behavior-change guardrail: registering "polygon" with the
    factory must not disturb "sahmk"'s own registration or selection."""
    from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider

    sahmk_provider = MarketDataProviderFactory.create("sahmk", "https://sahmk.example.invalid", "key")
    assert isinstance(sahmk_provider, SahmkMarketDataProvider)
