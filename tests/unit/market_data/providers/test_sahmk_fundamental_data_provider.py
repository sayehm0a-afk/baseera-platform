"""Unit tests for SahmkFundamentalDataProvider. SahmkMarketDataService
is replaced with an AsyncMock -- no network call is ever made."""

from unittest.mock import AsyncMock

import pytest

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.providers.fundamental_data_provider import (
    FundamentalDataProviderFactory,
    ProviderHealth,
)
from src.market_data.providers.sahmk_fundamental_data_provider import SahmkFundamentalDataProvider
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkEntitlementError,
    SahmkResponseValidationError,
)
from src.market_data.sahmk.models import SahmkCompanyProfile, SahmkDividend, SahmkFinancials


def _provider_with_mock_service():
    provider = SahmkFundamentalDataProvider(api_endpoint="https://sahmk.example.invalid", api_key="key")
    provider._service = AsyncMock()
    provider._service.has_credentials = True
    return provider


def _complete_financials(**overrides):
    defaults = dict(
        symbol="2222",
        period_type="annual",
        fiscal_period_end="2025-12-31",
        revenue=100.0,
        gross_profit=40.0,
        net_income=20.0,
        total_assets=500.0,
        total_liabilities=200.0,
        total_equity=300.0,
        current_assets=150.0,
        current_liabilities=80.0,
        inventory=10.0,
        cash_and_equivalents=30.0,
        total_debt=90.0,
        shares_outstanding=1000,
        eps=0.02,
        raw={},
    )
    defaults.update(overrides)
    return SahmkFinancials(**defaults)


# --- authenticate() -----------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_fails_fast_without_credentials():
    provider = SahmkFundamentalDataProvider(api_endpoint="x", api_key="")
    assert await provider.authenticate() is False


@pytest.mark.asyncio
async def test_authenticate_treats_entitlement_error_as_valid_key():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = SahmkEntitlementError("plan limit")
    assert await provider.authenticate() is True


# --- check_connectivity() -- raises instead of swallowing, unlike
# authenticate() above; used by fundamental_provider_factory's
# connectivity-probe retry. ------------------------------------------


@pytest.mark.asyncio
async def test_check_connectivity_succeeds():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.return_value = None
    assert await provider.check_connectivity() is True


@pytest.mark.asyncio
async def test_check_connectivity_treats_entitlement_error_as_valid_key():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = SahmkEntitlementError("plan limit")
    assert await provider.check_connectivity() is True


@pytest.mark.asyncio
async def test_check_connectivity_raises_on_rejected_key():
    provider = _provider_with_mock_service()
    provider._service.get_index_snapshot.side_effect = SahmkAuthenticationError("bad key")
    with pytest.raises(SahmkAuthenticationError):
        await provider.check_connectivity()


# --- get_fundamentals() -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_fundamentals_maps_to_dev_provider_compatible_shape():
    provider = _provider_with_mock_service()
    provider._service.get_financials.return_value = _complete_financials()
    provider._service.get_latest_dividend_per_share.return_value = 0.5

    data = await provider.get_fundamentals("2222", period_type="annual")

    assert data == {
        "symbol": "2222",
        "period_type": "annual",
        "fiscal_period_end": "2025-12-31",
        "revenue": 100.0,
        "gross_profit": 40.0,
        "net_income": 20.0,
        "total_assets": 500.0,
        "total_liabilities": 200.0,
        "total_equity": 300.0,
        "current_assets": 150.0,
        "current_liabilities": 80.0,
        "inventory": 10.0,
        "cash_and_equivalents": 30.0,
        "total_debt": 90.0,
        "shares_outstanding": 1000,
        "eps": 0.02,
        "dividend_per_share": 0.5,
        "source": "sahmk",
        "is_synthetic": False,
    }
    provider._service.get_financials.assert_awaited_once_with("2222", period_type="annual")


@pytest.mark.asyncio
async def test_get_fundamentals_defaults_dividend_per_share_to_zero_when_no_history():
    provider = _provider_with_mock_service()
    provider._service.get_financials.return_value = _complete_financials()
    provider._service.get_latest_dividend_per_share.return_value = None

    data = await provider.get_fundamentals("2222")
    assert data["dividend_per_share"] == 0


@pytest.mark.asyncio
async def test_get_fundamentals_raises_when_a_required_field_is_missing():
    provider = _provider_with_mock_service()
    provider._service.get_financials.return_value = _complete_financials(revenue=None)

    with pytest.raises(SahmkResponseValidationError, match="revenue"):
        await provider.get_fundamentals("2222")

    provider._service.get_latest_dividend_per_share.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_fundamentals_raises_when_fiscal_period_end_missing():
    provider = _provider_with_mock_service()
    provider._service.get_financials.return_value = _complete_financials(fiscal_period_end=None)

    with pytest.raises(SahmkResponseValidationError, match="fiscal_period_end"):
        await provider.get_fundamentals("2222")


@pytest.mark.asyncio
async def test_get_fundamentals_succeeds_when_current_assets_liabilities_shares_eps_are_missing():
    # The real, live SAHMK /financials/ response (confirmed for 3
    # symbols, workflow run 30436660246) never includes
    # current_assets/current_liabilities/shares_outstanding/eps --
    # this must not block ingestion of the fields SAHMK does provide.
    provider = _provider_with_mock_service()
    provider._service.get_financials.return_value = _complete_financials(
        current_assets=None, current_liabilities=None, shares_outstanding=None, eps=None,
    )
    provider._service.get_latest_dividend_per_share.return_value = None

    data = await provider.get_fundamentals("2222")

    assert data["revenue"] == 100.0
    assert data["current_assets"] is None
    assert data["current_liabilities"] is None
    assert data["shares_outstanding"] is None
    assert data["eps"] is None


# --- get_dividends() / get_company_profile() (extra, not part of interface) --


@pytest.mark.asyncio
async def test_get_dividends_maps_to_dicts():
    provider = _provider_with_mock_service()
    provider._service.get_dividends.return_value = [
        SahmkDividend("2222", 1.5, "2025-06-01", "2025-07-01", {})
    ]
    result = await provider.get_dividends("2222")
    assert result == [
        {
            "symbol": "2222",
            "dividend_per_share": 1.5,
            "ex_date": "2025-06-01",
            "payment_date": "2025-07-01",
            "source": "sahmk",
            "is_synthetic": False,
        }
    ]


@pytest.mark.asyncio
async def test_get_company_profile_maps_to_dict():
    provider = _provider_with_mock_service()
    provider._service.get_company_profile.return_value = SahmkCompanyProfile(
        "2222", "Saudi Aramco", None, "Energy", "Oil & Gas", "Tadawul", {}
    )
    result = await provider.get_company_profile("2222")
    assert result == {
        "symbol": "2222",
        "name": "Saudi Aramco",
        "sector": "Energy",
        "industry": "Oil & Gas",
        "exchange": "Tadawul",
        "source": "sahmk",
        "is_synthetic": False,
    }


# --- health_check() / disconnect() -----------------------------------------


@pytest.mark.asyncio
async def test_health_check_unhealthy_without_credentials():
    provider = SahmkFundamentalDataProvider(api_endpoint="x", api_key="")
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


@pytest.mark.asyncio
async def test_health_check_unhealthy_on_circuit_breaker_open():
    provider = _provider_with_mock_service()
    provider._service.check_health.side_effect = CircuitBreakerOpenError()
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


@pytest.mark.asyncio
async def test_disconnect_closes_service_and_resets_authenticated():
    provider = _provider_with_mock_service()
    provider.authenticated = True
    await provider.disconnect()
    provider._service.close.assert_awaited_once()
    assert provider.authenticated is False


# --- factory registration --------------------------------------------------


def test_provider_is_registered_with_factory():
    provider = FundamentalDataProviderFactory.create(
        "sahmk", api_endpoint="https://sahmk.example.invalid", api_key="key"
    )
    assert isinstance(provider, SahmkFundamentalDataProvider)
