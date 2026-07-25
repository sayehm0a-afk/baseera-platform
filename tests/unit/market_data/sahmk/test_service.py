"""Unit tests for SahmkMarketDataService -- SahmkClient is mocked
directly, no network involved."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.market_data.sahmk.exceptions import SahmkResponseValidationError
from src.market_data.sahmk.models import (
    SahmkCompanyProfile,
    SahmkDividend,
    SahmkEvent,
    SahmkHistoricalBar,
    SahmkMarketSummary,
    SahmkQuote,
)
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


# --- get_company_profile ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_profile_parses_known_field_names():
    client = AsyncMock()
    client.get_company_profile.return_value = {"name": "Saudi Aramco", "sector": "Energy"}
    service = _service(client)
    profile = await service.get_company_profile("2222")
    assert profile == SahmkCompanyProfile(
        symbol="2222", name="Saudi Aramco", sector="Energy", raw={"name": "Saudi Aramco", "sector": "Energy"}
    )


@pytest.mark.asyncio
async def test_get_company_profile_tolerates_missing_fields():
    client = AsyncMock()
    client.get_company_profile.return_value = {}
    service = _service(client)
    profile = await service.get_company_profile("2222")
    assert profile.name is None
    assert profile.sector is None


# --- get_financials ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_financials_parses_primary_field_names():
    client = AsyncMock()
    client.get_financials.return_value = {
        "fiscal_period_end": "2025-12-31",
        "revenue": 100.0,
        "net_income": 20.0,
        "total_assets": 500.0,
        "total_liabilities": 200.0,
        "total_equity": 300.0,
        "current_assets": 150.0,
        "current_liabilities": 80.0,
        "shares_outstanding": 1000,
        "eps": 0.02,
    }
    service = _service(client)
    financials = await service.get_financials("2222", period_type="annual")
    assert financials.revenue == 100.0
    assert financials.net_income == 20.0
    assert financials.shares_outstanding == 1000
    assert financials.eps == 0.02
    assert financials.period_type == "annual"
    client.get_financials.assert_awaited_once_with("2222", period_type="annual")


@pytest.mark.asyncio
async def test_get_financials_falls_back_to_alternate_field_names():
    client = AsyncMock()
    client.get_financials.return_value = {
        "period_end": "2025-12-31",
        "total_revenue": 100.0,
        "net_profit": 20.0,
        "shareholders_equity": 300.0,
        "shares": 1000,
        "earnings_per_share": 0.02,
    }
    service = _service(client)
    financials = await service.get_financials("2222")
    assert financials.fiscal_period_end == "2025-12-31"
    assert financials.revenue == 100.0
    assert financials.net_income == 20.0
    assert financials.total_equity == 300.0
    assert financials.shares_outstanding == 1000
    assert financials.eps == 0.02


@pytest.mark.asyncio
async def test_get_financials_never_raises_on_missing_fields_and_keeps_raw():
    client = AsyncMock()
    client.get_financials.return_value = {"unexpected_field": "x"}
    service = _service(client)
    financials = await service.get_financials("2222")
    assert financials.revenue is None
    assert financials.raw == {"unexpected_field": "x"}


@pytest.mark.asyncio
async def test_get_financials_is_cached_per_symbol_and_period():
    client = AsyncMock()
    client.get_financials.return_value = {"revenue": 1}
    service = _service(client)
    await service.get_financials("2222", period_type="annual")
    await service.get_financials("2222", period_type="annual")
    client.get_financials.assert_awaited_once()


# --- get_dividends / get_latest_dividend_per_share ------------------------


@pytest.mark.asyncio
async def test_get_dividends_parses_dividends_key():
    first = {"dividend_per_share": 1.5, "ex_date": "2025-06-01", "payment_date": "2025-07-01"}
    second = {"dividend_per_share": 1.2, "ex_date": "2024-06-01", "payment_date": "2024-07-01"}
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": [first, second]}
    service = _service(client)
    dividends = await service.get_dividends("2222")
    assert dividends == [
        SahmkDividend("2222", 1.5, "2025-06-01", "2025-07-01", first),
        SahmkDividend("2222", 1.2, "2024-06-01", "2024-07-01", second),
    ]


@pytest.mark.asyncio
async def test_get_dividends_falls_back_to_results_and_amount_field():
    client = AsyncMock()
    client.get_dividends.return_value = {"results": [{"amount": 2.0}]}
    service = _service(client)
    dividends = await service.get_dividends("2222")
    assert dividends[0].dividend_per_share == 2.0


@pytest.mark.asyncio
async def test_get_dividends_skips_entries_with_no_amount():
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": [{"ex_date": "2025-01-01"}]}
    service = _service(client)
    dividends = await service.get_dividends("2222")
    assert dividends == []


@pytest.mark.asyncio
async def test_get_latest_dividend_per_share_returns_most_recent():
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": [{"dividend_per_share": 1.5}]}
    service = _service(client)
    assert await service.get_latest_dividend_per_share("2222") == 1.5


@pytest.mark.asyncio
async def test_get_latest_dividend_per_share_none_when_no_history():
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": []}
    service = _service(client)
    assert await service.get_latest_dividend_per_share("2222") is None


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
