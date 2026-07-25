"""Unit tests for src.market_data.provider_factory -- the network-aware
auto-selection logic. SahmkMarketDataProvider is replaced with a fake so
no network call is ever made; these tests only exercise the selection
policy (env var overrides, connectivity/auth outcomes, caching)."""

import asyncio

import pytest

from src.market_data import provider_factory
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkRequestError


class _FakeSahmkProvider:
    """Stands in for SahmkMarketDataProvider in provider_factory tests."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.disconnected = False
        _FakeSahmkProvider.instances.append(self)

    async def authenticate(self):
        raise NotImplementedError  # each test overrides this on the instance

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    _FakeSahmkProvider.instances.clear()
    monkeypatch.setattr(provider_factory, "SahmkMarketDataProvider", _FakeSahmkProvider)
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60")
    yield
    provider_factory.reset_provider_cache()


@pytest.mark.asyncio
async def test_forced_dev_returns_dev_provider_even_with_credentials(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert provider_factory.get_last_selected_provider_kind() == "dev"
    assert _FakeSahmkProvider.instances == []


@pytest.mark.asyncio
async def test_auto_without_credentials_returns_dev_provider():
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert provider_factory.get_last_selected_provider_kind() == "dev"


@pytest.mark.asyncio
async def test_forced_sahmk_without_credentials_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)


@pytest.mark.asyncio
async def test_auto_with_credentials_and_reachable_sahmk_returns_sahmk_provider(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.authenticate = lambda self: _ok()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, _FakeSahmkProvider)
    assert provider_factory.get_last_selected_provider_kind() == "sahmk"


@pytest.mark.asyncio
async def test_auto_with_credentials_but_rejected_key_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_bad")

    async def _rejected():
        return False

    _FakeSahmkProvider.authenticate = lambda self: _rejected()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert _FakeSahmkProvider.instances[0].disconnected is True


@pytest.mark.asyncio
async def test_auto_with_credentials_but_unreachable_host_falls_back_to_dev(monkeypatch):
    """This is the exact scenario the network-restricted sandbox produces:
    a configured key, but the host cannot be reached."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _network_error():
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    _FakeSahmkProvider.authenticate = lambda self: _network_error()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert provider_factory.get_last_selected_provider_kind() == "dev"


@pytest.mark.asyncio
async def test_auto_with_credentials_probe_timeout_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _hangs():
        await asyncio.sleep(10)
        return True

    _FakeSahmkProvider.authenticate = lambda self: _hangs()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)


@pytest.mark.asyncio
async def test_selection_is_cached_across_calls(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.authenticate = lambda self: _ok()

    await provider_factory.get_market_data_provider()
    await provider_factory.get_market_data_provider()
    assert len(_FakeSahmkProvider.instances) == 1  # second call served from cache


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.authenticate = lambda self: _ok()

    await provider_factory.get_market_data_provider()
    await provider_factory.get_market_data_provider(force_refresh=True)
    assert len(_FakeSahmkProvider.instances) == 2


@pytest.mark.asyncio
async def test_get_last_selected_provider_kind_none_before_any_selection():
    assert provider_factory.get_last_selected_provider_kind() is None
