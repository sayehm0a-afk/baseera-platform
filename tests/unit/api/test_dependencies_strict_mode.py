"""Unit tests for src.api.dependencies' provider dependencies under
strict real-data mode: StrictRealDataUnavailableError must never reach
a route as a bare/unhandled exception -- it is translated into the
existing ProviderUnavailableError (503) so every route that depends on
a market/fundamental provider (quote/history/stock-detail/
recommendation/decision/analyst-report) fails clearly instead of
either crashing unhandled or ever serving synthetic data as real.
"""

import pytest

from src.api.dependencies import get_fundamental_provider, get_market_provider
from src.api.exceptions import ProviderUnavailableError
from src.market_data import fundamental_provider_factory, provider_factory


class _FakeSahmkProvider:
    def __init__(self, *args, **kwargs):
        pass

    async def authenticate(self):
        return False

    async def check_connectivity(self):
        return False

    async def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    fundamental_provider_factory.reset_fundamental_provider_cache()
    monkeypatch.setattr(provider_factory, "SahmkMarketDataProvider", _FakeSahmkProvider)
    monkeypatch.setattr(fundamental_provider_factory, "SahmkFundamentalDataProvider", _FakeSahmkProvider)
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("SAHMK_PROBE_MAX_ATTEMPTS", "1")
    yield
    provider_factory.reset_provider_cache()
    fundamental_provider_factory.reset_fundamental_provider_cache()


@pytest.mark.asyncio
async def test_get_market_provider_raises_provider_unavailable_not_a_bare_exception():
    with pytest.raises(ProviderUnavailableError) as excinfo:
        await get_market_provider()
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_get_fundamental_provider_raises_provider_unavailable_not_a_bare_exception():
    with pytest.raises(ProviderUnavailableError) as excinfo:
        await get_fundamental_provider()
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "provider_unavailable"
