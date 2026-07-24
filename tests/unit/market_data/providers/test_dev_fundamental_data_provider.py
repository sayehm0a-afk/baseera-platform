"""Unit tests for DevFundamentalDataProvider -- deterministic synthetic
data, no network."""

import pytest

from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider
from src.market_data.providers.fundamental_data_provider import (
    FundamentalDataProviderFactory,
    ProviderHealth,
)


@pytest.fixture
def provider():
    return DevFundamentalDataProvider()


@pytest.mark.asyncio
async def test_authenticate_always_succeeds(provider):
    assert await provider.authenticate() is True


@pytest.mark.asyncio
async def test_get_fundamentals_is_labeled_synthetic(provider):
    data = await provider.get_fundamentals("2222")
    assert data["symbol"] == "2222"
    assert data["source"] == "dev-synthetic"
    assert data["is_synthetic"] is True


@pytest.mark.asyncio
async def test_get_fundamentals_balance_sheet_identity_holds(provider):
    data = await provider.get_fundamentals("2222")
    # total_liabilities is constructed as total_assets - total_equity,
    # so assets == liabilities + equity must hold exactly.
    assert data["total_assets"] == pytest.approx(data["total_liabilities"] + data["total_equity"])


@pytest.mark.asyncio
async def test_get_fundamentals_values_are_positive_and_plausible(provider):
    data = await provider.get_fundamentals("2222")
    assert data["revenue"] > 0
    assert data["total_assets"] > 0
    assert data["total_equity"] > 0
    assert data["shares_outstanding"] > 0
    assert data["current_assets"] <= data["total_assets"]
    assert data["current_liabilities"] <= data["total_liabilities"] + data["total_equity"]


@pytest.mark.asyncio
async def test_get_fundamentals_is_deterministic_for_same_symbol_and_period(provider):
    first = await provider.get_fundamentals("2222", period_type="annual")
    second = await provider.get_fundamentals("2222", period_type="annual")
    assert first == second


@pytest.mark.asyncio
async def test_get_fundamentals_differs_across_symbols(provider):
    a = await provider.get_fundamentals("2222")
    b = await provider.get_fundamentals("1010")
    assert a["revenue"] != b["revenue"]


@pytest.mark.asyncio
async def test_get_fundamentals_quarterly_revenue_smaller_than_annual(provider):
    annual = await provider.get_fundamentals("2222", period_type="annual")
    quarterly = await provider.get_fundamentals("2222", period_type="quarterly")
    assert quarterly["revenue"] < annual["revenue"]
    assert quarterly["fiscal_period_end"] != annual["fiscal_period_end"]


@pytest.mark.asyncio
async def test_get_fundamentals_rejects_unsupported_period_type(provider):
    with pytest.raises(ValueError):
        await provider.get_fundamentals("2222", period_type="monthly")


@pytest.mark.asyncio
async def test_health_check_reflects_authentication_state(provider):
    assert await provider.health_check() == ProviderHealth.UNHEALTHY
    await provider.authenticate()
    assert await provider.health_check() == ProviderHealth.HEALTHY
    await provider.disconnect()
    assert await provider.health_check() == ProviderHealth.UNHEALTHY


def test_provider_is_registered_with_factory():
    provider = FundamentalDataProviderFactory.create("dev")
    assert isinstance(provider, DevFundamentalDataProvider)
