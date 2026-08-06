"""Unit tests for SahmkMarketDataProvider -- the IMarketDataProvider
adapter. SahmkMarketDataService is replaced with an AsyncMock so no
network call is ever made; assertions focus on the adapter's own
mapping/error-translation logic (already covered independently by
test_client.py and test_service.py)."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.providers.market_data_provider import MarketDataProviderFactory, ProviderHealth
from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkEntitlementError,
)
from src.market_data.sahmk.models import (
    SahmkCompanyProfile,
    SahmkEvent,
    SahmkHistoricalBar,
    SahmkMarketSummary,
    SahmkQuote,
)


def _provider_with_mock_service():
    provider = SahmkMarketDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")
    provider._service = AsyncMock()
    provider._service.has_credentials = True
    return provider


# --- authenticate() -----------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_fails_fast_without_credentials():
    provider = SahmkMarketDataProvider(api_endpoint="x", api_key="")
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_succeeds_on_valid_key():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.return_value = SahmkMarketSummary("TASI", 1.0, None, None, None)
    result = await provider.authenticate()
    assert result is True
    assert provider.authenticated is True
    provider._service.get_index_snapshot.assert_awaited_once_with("TASI")


@pytest.mark.asyncio
async def test_authenticate_treats_entitlement_error_as_valid_key():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = SahmkEntitlementError("plan limit")
    result = await provider.authenticate()
    assert result is True
    assert provider.authenticated is True


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_rejected_key():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = SahmkAuthenticationError("bad key")
    result = await provider.authenticate()
    assert result is False
    assert provider.authenticated is False


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_configuration_error():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = SahmkConfigurationError("no key")
    result = await provider.authenticate()
    assert result is False


@pytest.mark.asyncio
async def test_authenticate_returns_false_when_circuit_breaker_open():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = CircuitBreakerOpenError()
    result = await provider.authenticate()
    assert result is False


# --- get_stock_data() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_stock_data_maps_bar_to_ohlcv_dict():
    provider = _provider_with_mock_service()
    provider._service.get_daily_bar.return_value = SahmkHistoricalBar(
        symbol="1120",
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=1000,
        timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    data = await provider.get_stock_data("1120")
    assert data == {
        "symbol": "1120",
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 1000,
        "timestamp": "2026-01-05T00:00:00+00:00",
        "source": "sahmk",
        "is_synthetic": False,
    }


# --- get_historical_ohlcv() -----------------------------------------------


@pytest.mark.asyncio
async def test_get_historical_ohlcv_maps_every_bar():
    provider = _provider_with_mock_service()
    provider._service.get_historical_bars.return_value = [
        SahmkHistoricalBar("1120", 10.0, 11.0, 9.5, 10.5, 1000, datetime(2026, 1, 5, tzinfo=timezone.utc)),
        SahmkHistoricalBar("1120", 10.5, 12.0, 10.0, 11.5, 1200, datetime(2026, 1, 6, tzinfo=timezone.utc)),
    ]

    bars = await provider.get_historical_ohlcv("1120", date(2026, 1, 5), date(2026, 1, 6))

    assert bars == [
        {
            "symbol": "1120", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5,
            "volume": 1000, "timestamp": "2026-01-05T00:00:00+00:00",
            "source": "sahmk", "is_synthetic": False,
        },
        {
            "symbol": "1120", "open": 10.5, "high": 12.0, "low": 10.0, "close": 11.5,
            "volume": 1200, "timestamp": "2026-01-06T00:00:00+00:00",
            "source": "sahmk", "is_synthetic": False,
        },
    ]
    provider._service.get_historical_bars.assert_awaited_once_with(
        "1120", date(2026, 1, 5), date(2026, 1, 6), interval="1d"
    )


@pytest.mark.asyncio
async def test_get_historical_ohlcv_empty_list_when_no_bars():
    provider = _provider_with_mock_service()
    provider._service.get_historical_bars.return_value = []
    bars = await provider.get_historical_ohlcv("1120", date(2026, 1, 5), date(2026, 1, 6))
    assert bars == []


# --- get_latest_quote() (extra, not part of IMarketDataProvider) ---------


@pytest.mark.asyncio
async def test_get_latest_quote_maps_quote_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_latest_quote.return_value = SahmkQuote(
        symbol="1120",
        price=10.5,
        change=0.1,
        change_percent=0.9,
        volume=500,
        timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    data = await provider.get_latest_quote("1120")
    assert data["price"] == 10.5
    assert data["source"] == "sahmk"
    assert data["is_synthetic"] is False


# --- get_symbol_directory() (extra, not part of IMarketDataProvider) -------


@pytest.mark.asyncio
async def test_get_symbol_directory_maps_companies_to_dicts():
    provider = _provider_with_mock_service()
    provider._service.get_company_directory.return_value = [
        SahmkCompanyProfile(
            symbol="2222", name="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy",
            industry="Oil & Gas", exchange="Tadawul", raw={},
        ),
        SahmkCompanyProfile(
            symbol="1120", name="Al Rajhi Bank", name_ar=None, sector="Financials", industry=None,
            exchange="Tadawul", raw={},
        ),
    ]
    directory = await provider.get_symbol_directory()
    assert directory == [
        {
            "symbol": "2222", "name": "Saudi Aramco", "name_ar": "أرامكو السعودية", "sector": "Energy",
            "industry": "Oil & Gas", "exchange": "Tadawul", "source": "sahmk", "is_synthetic": False,
            "is_eligible": True, "instrument_bucket": "MAIN_MARKET_EQUITY_TYPE_UNCONFIRMED",
            "exclusion_reason": None,
        },
        {
            "symbol": "1120", "name": "Al Rajhi Bank", "name_ar": None, "sector": "Financials", "industry": None,
            "exchange": "Tadawul", "source": "sahmk", "is_synthetic": False,
            "is_eligible": True, "instrument_bucket": "MAIN_MARKET_EQUITY_TYPE_UNCONFIRMED",
            "exclusion_reason": None,
        },
    ]


@pytest.mark.asyncio
async def test_get_symbol_directory_excludes_a_confirmed_etf_via_is_eligible():
    """Root-cause repair: a discovered ETF must carry is_eligible=False
    (via universe_policy.classify_universe on the raw is_etf field) so
    ingest_symbols.sync_symbols can deactivate its Stock row instead of
    letting it pollute the scan universe as if it were a common stock."""
    provider = _provider_with_mock_service()
    provider._service.get_company_directory.return_value = [
        SahmkCompanyProfile(
            symbol="2222", name="Saudi Aramco", name_ar=None, sector=None, industry=None,
            exchange=None, raw={"is_etf": False, "security_type": "Common Share"},
        ),
        SahmkCompanyProfile(
            symbol="4342", name="Some ETF Fund", name_ar=None, sector=None, industry=None,
            exchange=None, raw={"is_etf": True},
        ),
    ]

    directory = await provider.get_symbol_directory()
    by_symbol = {d["symbol"]: d for d in directory}

    assert by_symbol["2222"]["is_eligible"] is True
    assert by_symbol["4342"]["is_eligible"] is False
    assert by_symbol["4342"]["instrument_bucket"] == "ETF_FUND"
    assert by_symbol["4342"]["exclusion_reason"] == "is_etf=True (raw=True)"

    # The full classification breakdown is retained for admin/coverage
    # reporting, not just used-and-discarded.
    assert provider.last_universe_classification is not None
    assert provider.last_universe_classification.total_instruments == 2
    assert provider.last_universe_classification.total_eligible == 1
    assert provider.last_universe_classification.bucket_counts["ETF_FUND"] == 1


# --- get_company_profile() (extra, not part of IMarketDataProvider) --------


@pytest.mark.asyncio
async def test_get_company_profile_maps_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_company_profile.return_value = SahmkCompanyProfile(
        symbol="2222", name="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy",
        industry="Oil & Gas", exchange="Tadawul", raw={},
    )
    profile = await provider.get_company_profile("2222")
    assert profile == {
        "symbol": "2222",
        "name": "Saudi Aramco",
        "name_ar": "أرامكو السعودية",
        "sector": "Energy",
        "industry": "Oil & Gas",
        "exchange": "Tadawul",
        "source": "sahmk",
        "is_synthetic": False,
    }


# --- get_index_data() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_data_maps_summary_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.return_value = SahmkMarketSummary(
        index="TASI",
        value=12000.0,
        change=10.0,
        change_percent=0.1,
        timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    data = await provider.get_index_data("TASI")
    assert data["index_name"] == "TASI"
    assert data["value"] == 12000.0
    assert data["source"] == "sahmk"
    assert data["is_synthetic"] is False


# --- get_market_news() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_news_maps_events_to_dicts():
    provider = _provider_with_mock_service()
    provider._service.get_recent_events.return_value = [
        SahmkEvent(symbol="1120", headline="Headline", timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc), raw={})
    ]
    news = await provider.get_market_news(limit=1)
    assert news == [
        {
            "headline": "Headline",
            "symbol": "1120",
            "timestamp": "2026-01-05T00:00:00+00:00",
            "source": "sahmk",
            "is_synthetic": False,
        }
    ]
    provider._service.get_recent_events.assert_awaited_once_with(limit=1)


# --- health_check() -----------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_unhealthy_without_credentials():
    provider = SahmkMarketDataProvider(api_endpoint="x", api_key="")
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
    provider = MarketDataProviderFactory.create("sahmk", "https://sahmk.example.invalid", "key")
    assert isinstance(provider, SahmkMarketDataProvider)
