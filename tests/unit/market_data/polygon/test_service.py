"""Unit tests for PolygonMarketDataService. PolygonClient is replaced
with an AsyncMock so no network call is ever made -- assertions focus
on parsing raw dicts into typed models and caching, mirroring
tests/unit/market_data/sahmk/test_service.py's style."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.polygon.exceptions import PolygonResponseValidationError
from src.market_data.polygon.models import (
    PolygonBar,
    PolygonMarketStatus,
    PolygonNewsItem,
    PolygonTickerDetails,
)
from src.market_data.polygon.service import PolygonMarketDataService


def _service():
    client = AsyncMock()
    service = PolygonMarketDataService(client=client, cache=TTLCache())
    return service, client


# --- get_previous_close() ---------------------------------------------


@pytest.mark.asyncio
async def test_get_previous_close_parses_bar():
    service, client = _service()
    client.get_previous_close.return_value = {
        "results": [{"o": 148.0, "h": 151.0, "l": 147.5, "c": 150.0, "v": 1000000, "t": 1735689600000}]
    }
    bar = await service.get_previous_close("AAPL")
    assert bar == PolygonBar(
        ticker="AAPL",
        open=148.0,
        high=151.0,
        low=147.5,
        close=150.0,
        volume=1000000.0,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        vwap=None,
        transactions=None,
        raw={"o": 148.0, "h": 151.0, "l": 147.5, "c": 150.0, "v": 1000000, "t": 1735689600000},
    )


@pytest.mark.asyncio
async def test_get_previous_close_raises_on_empty_results():
    service, client = _service()
    client.get_previous_close.return_value = {"results": []}
    with pytest.raises(PolygonResponseValidationError):
        await service.get_previous_close("AAPL")


@pytest.mark.asyncio
async def test_get_previous_close_raises_on_missing_required_field():
    service, client = _service()
    client.get_previous_close.return_value = {"results": [{"o": 1, "h": 2, "l": 0.5}]}  # missing c/v/t
    with pytest.raises(PolygonResponseValidationError):
        await service.get_previous_close("AAPL")


@pytest.mark.asyncio
async def test_get_previous_close_is_cached():
    service, client = _service()
    client.get_previous_close.return_value = {
        "results": [{"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100, "t": 1735689600000}]
    }
    await service.get_previous_close("AAPL")
    await service.get_previous_close("AAPL")
    client.get_previous_close.assert_awaited_once()


# --- get_aggregates() / get_daily_bar() --------------------------------


@pytest.mark.asyncio
async def test_get_aggregates_parses_every_bar():
    service, client = _service()
    client.get_aggregates.return_value = {
        "results": [
            {"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100, "t": 1735689600000},
            {"o": 1.5, "h": 2.5, "l": 1.0, "c": 2.0, "v": 200, "t": 1735776000000, "vw": 1.9, "n": 50},
        ]
    }
    bars = await service.get_aggregates("AAPL", date(2026, 1, 1), date(2026, 1, 2))
    assert len(bars) == 2
    assert bars[0].close == 1.5
    assert bars[1].vwap == 1.9
    assert bars[1].transactions == 50


@pytest.mark.asyncio
async def test_get_aggregates_empty_list_when_no_bars():
    service, client = _service()
    client.get_aggregates.return_value = {"results": []}
    bars = await service.get_aggregates("AAPL", date(2026, 1, 1), date(2026, 1, 2))
    assert bars == []


@pytest.mark.asyncio
async def test_get_daily_bar_returns_the_last_bar():
    service, client = _service()
    client.get_aggregates.return_value = {
        "results": [{"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100, "t": 1735689600000}]
    }
    bar = await service.get_daily_bar("AAPL", on=date(2026, 1, 1))
    assert bar.close == 1.5


@pytest.mark.asyncio
async def test_get_daily_bar_raises_when_no_bar_available():
    service, client = _service()
    client.get_aggregates.return_value = {"results": []}
    with pytest.raises(PolygonResponseValidationError):
        await service.get_daily_bar("AAPL", on=date(2026, 1, 1))


# --- get_ticker_details() -----------------------------------------------


@pytest.mark.asyncio
async def test_get_ticker_details_parses_result():
    service, client = _service()
    client.get_ticker_details.return_value = {
        "results": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "stocks",
            "locale": "us",
            "primary_exchange": "XNAS",
            "type": "CS",
            "active": True,
            "currency_name": "usd",
            "market_cap": 3000000000000.0,
            "description": "Apple designs...",
        }
    }
    details = await service.get_ticker_details("AAPL")
    assert details == PolygonTickerDetails(
        ticker="AAPL",
        name="Apple Inc.",
        market="stocks",
        locale="us",
        primary_exchange="XNAS",
        type="CS",
        active=True,
        currency_name="usd",
        market_cap=3000000000000.0,
        description="Apple designs...",
        raw=client.get_ticker_details.return_value["results"],
    )


@pytest.mark.asyncio
async def test_get_ticker_details_raises_when_ticker_field_missing():
    service, client = _service()
    client.get_ticker_details.return_value = {"results": {"name": "no ticker field"}}
    with pytest.raises(PolygonResponseValidationError):
        await service.get_ticker_details("AAPL")


# --- get_ticker_directory() ----------------------------------------------


@pytest.mark.asyncio
async def test_get_ticker_directory_parses_every_entry():
    service, client = _service()
    client.get_tickers.return_value = {
        "results": [
            {"ticker": "AAPL", "name": "Apple Inc.", "market": "stocks", "active": True},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "market": "stocks", "active": True},
        ],
        "count": 2,
    }
    directory = await service.get_ticker_directory()
    assert [d.ticker for d in directory] == ["AAPL", "MSFT"]
    assert directory[0].market_cap is None  # not present on the bulk directory shape


@pytest.mark.asyncio
async def test_get_ticker_directory_skips_entries_without_a_ticker():
    service, client = _service()
    client.get_tickers.return_value = {"results": [{"name": "no ticker"}, {"ticker": "AAPL"}]}
    directory = await service.get_ticker_directory()
    assert [d.ticker for d in directory] == ["AAPL"]


# --- get_ticker_news() ----------------------------------------------------


@pytest.mark.asyncio
async def test_get_ticker_news_parses_articles():
    service, client = _service()
    client.get_ticker_news.return_value = {
        "results": [
            {
                "id": "abc",
                "title": "Apple announces...",
                "tickers": ["AAPL"],
                "published_utc": "2026-01-05T12:00:00Z",
                "article_url": "https://example.invalid/a",
                "publisher": {"name": "Reuters"},
            }
        ]
    }
    news = await service.get_ticker_news(ticker="AAPL", limit=1)
    assert news == [
        PolygonNewsItem(
            id="abc",
            title="Apple announces...",
            tickers=["AAPL"],
            published_utc=datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc),
            article_url="https://example.invalid/a",
            publisher_name="Reuters",
            raw=client.get_ticker_news.return_value["results"][0],
        )
    ]
    client.get_ticker_news.assert_awaited_once_with(ticker="AAPL", limit=1)


@pytest.mark.asyncio
async def test_get_ticker_news_defaults_missing_title_to_empty_string():
    service, client = _service()
    client.get_ticker_news.return_value = {"results": [{"id": "x", "tickers": []}]}
    news = await service.get_ticker_news()
    assert news[0].title == ""
    assert news[0].publisher_name is None


# --- get_market_status() --------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_status_parses_snapshot():
    service, client = _service()
    client.get_market_status.return_value = {
        "market": "open",
        "serverTime": "2026-01-05T14:30:00-05:00",
        "exchanges": {"nasdaq": "open", "nyse": "open"},
    }
    status = await service.get_market_status()
    assert status.market == "open"
    assert status.exchanges == {"nasdaq": "open", "nyse": "open"}
    assert status.server_time is not None


# --- check_health() --------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_true_on_success():
    service, client = _service()
    client.get_market_status.return_value = {"market": "open", "exchanges": {}}
    assert await service.check_health() is True


@pytest.mark.asyncio
async def test_check_health_false_on_any_failure():
    service, client = _service()
    client.get_market_status.side_effect = RuntimeError("boom")
    assert await service.check_health() is False


# --- has_credentials / close proxy to the client ---------------------------


@pytest.mark.asyncio
async def test_has_credentials_proxies_client():
    service, client = _service()
    client.has_credentials = True
    assert service.has_credentials is True


@pytest.mark.asyncio
async def test_close_proxies_client():
    service, client = _service()
    await service.close()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_context_manager_closes_on_exit():
    service, client = _service()
    async with service:
        pass
    client.close.assert_awaited_once()


def test_polygon_market_status_model_carries_raw():
    status = PolygonMarketStatus(market="open", server_time=None, exchanges={}, raw={"market": "open"})
    assert status.raw == {"market": "open"}
