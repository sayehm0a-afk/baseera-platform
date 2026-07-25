"""Unit tests for SahmkMarketDataService -- SahmkClient is mocked
directly, no network involved."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.market_data.sahmk.exceptions import SahmkResponseValidationError
from src.market_data.sahmk.models import SahmkEvent, SahmkHistoricalBar, SahmkMarketSummary, SahmkQuote
from src.market_data.sahmk.service import SahmkMarketDataService


def _service(client=None):
    return SahmkMarketDataService(client=client or AsyncMock())


# --- get_latest_quote ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_quote_parses_full_response():
    client = AsyncMock()
    client.get_quote.return_value = {
        "price": 42.5,
        "change": 1.2,
        "change_percent": 2.9,
        "volume": 1000,
        "timestamp": "2026-01-05T12:00:00Z",
    }
    service = _service(client)
    quote = await service.get_latest_quote("1120")
    assert quote == SahmkQuote(
        symbol="1120",
        price=42.5,
        change=1.2,
        change_percent=2.9,
        volume=1000,
        timestamp=datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_latest_quote_tolerates_missing_optional_fields():
    client = AsyncMock()
    client.get_quote.return_value = {"price": 10.0}
    service = _service(client)
    quote = await service.get_latest_quote("1120")
    assert quote.price == 10.0
    assert quote.change is None
    assert quote.volume is None


@pytest.mark.asyncio
async def test_get_latest_quote_raises_when_price_missing():
    client = AsyncMock()
    client.get_quote.return_value = {"volume": 100}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_latest_quote("1120")


@pytest.mark.asyncio
async def test_get_latest_quote_is_cached():
    client = AsyncMock()
    client.get_quote.return_value = {"price": 1.0}
    service = _service(client)
    await service.get_latest_quote("1120")
    await service.get_latest_quote("1120")
    client.get_quote.assert_awaited_once_with("1120")


# --- get_historical_bars / get_daily_bar ------------------------------------


@pytest.mark.asyncio
async def test_get_historical_bars_parses_every_bar():
    client = AsyncMock()
    client.get_historical.return_value = {
        "bars": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "timestamp": "2026-01-05T00:00:00Z"},
            {"open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 20, "timestamp": "2026-01-06T00:00:00Z"},
        ]
    }
    service = _service(client)
    bars = await service.get_historical_bars("1120", date(2026, 1, 5), date(2026, 1, 6))
    assert bars == [
        SahmkHistoricalBar("1120", 1.0, 2.0, 0.5, 1.5, 10, datetime(2026, 1, 5, tzinfo=timezone.utc)),
        SahmkHistoricalBar("1120", 2.0, 3.0, 1.5, 2.5, 20, datetime(2026, 1, 6, tzinfo=timezone.utc)),
    ]


@pytest.mark.asyncio
async def test_get_historical_bars_raises_on_bar_missing_required_field():
    client = AsyncMock()
    client.get_historical.return_value = {"bars": [{"open": 1, "close": 1.5}]}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_historical_bars("1120", date(2026, 1, 5), date(2026, 1, 5))


@pytest.mark.asyncio
async def test_get_daily_bar_returns_last_bar():
    client = AsyncMock()
    client.get_historical.return_value = {
        "bars": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "timestamp": "t1"},
            {"open": 2, "high": 3, "low": 1.5, "close": 2.9, "volume": 20, "timestamp": "t2"},
        ]
    }
    service = _service(client)
    bar = await service.get_daily_bar("1120", on=date(2026, 1, 5))
    assert bar.close == 2.9


@pytest.mark.asyncio
async def test_get_daily_bar_raises_when_no_bars_returned():
    client = AsyncMock()
    client.get_historical.return_value = {"bars": []}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_daily_bar("1120", on=date(2026, 1, 5))


# --- get_index_snapshot ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_snapshot_parses_response():
    client = AsyncMock()
    client.get_market_summary.return_value = {
        "index_value": 12000.5,
        "index_change": 50.0,
        "index_change_percent": 0.42,
        "timestamp": "2026-01-05T15:00:00Z",
    }
    service = _service(client)
    summary = await service.get_index_snapshot("TASI")
    assert summary == SahmkMarketSummary(
        index="TASI",
        value=12000.5,
        change=50.0,
        change_percent=0.42,
        timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_index_snapshot_raises_when_index_value_missing():
    client = AsyncMock()
    client.get_market_summary.return_value = {}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_index_snapshot("TASI")


# --- get_recent_events --------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_events_parses_events_key():
    client = AsyncMock()
    client.get_events.return_value = {
        "events": [{"symbol": "1120", "headline": "Big news", "timestamp": "2026-01-05T00:00:00Z"}]
    }
    service = _service(client)
    events = await service.get_recent_events(limit=1)
    assert events == [
        SahmkEvent(
            symbol="1120",
            headline="Big news",
            timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
            raw={"symbol": "1120", "headline": "Big news", "timestamp": "2026-01-05T00:00:00Z"},
        )
    ]


@pytest.mark.asyncio
async def test_get_recent_events_falls_back_to_results_key_and_title_field():
    client = AsyncMock()
    client.get_events.return_value = {"results": [{"title": "Fallback headline"}]}
    service = _service(client)
    events = await service.get_recent_events(limit=1)
    assert events[0].headline == "Fallback headline"
    assert events[0].symbol is None


# --- check_health ------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_true_on_success():
    client = AsyncMock()
    client.get_market_summary.return_value = {"index_value": 1}
    service = _service(client)
    assert await service.check_health() is True


@pytest.mark.asyncio
async def test_check_health_false_on_any_failure():
    client = AsyncMock()
    client.get_market_summary.side_effect = RuntimeError("boom")
    service = _service(client)
    assert await service.check_health() is False


@pytest.mark.asyncio
async def test_close_delegates_to_client():
    client = AsyncMock()
    service = _service(client)
    await service.close()
    client.close.assert_awaited_once()


def test_has_credentials_delegates_to_client():
    client = AsyncMock()
    client.has_credentials = True
    service = _service(client)
    assert service.has_credentials is True
