"""Unit tests for src.market_data.fundamental_provider_factory -- mirrors
test_provider_factory.py's approach for the fundamentals provider
family. SahmkFundamentalDataProvider is replaced with a fake so no
network call is ever made."""

import asyncio

import pytest

from src.market_data import fundamental_provider_factory
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider
from src.market_data.sahmk.exceptions import SahmkRequestError


class _FakeSahmkFundamentalProvider:
    instances = []

    def __init__(self, *args, **kwargs):
        self.disconnected = False
        _FakeSahmkFundamentalProvider.instances.append(self)

    async def authenticate(self):
        raise NotImplementedError

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    fundamental_provider_factory.reset_fundamental_provider_cache()
    _FakeSahmkFundamentalProvider.instances.clear()
    monkeypatch.setattr(
        fundamental_provider_factory, "SahmkFundamentalDataProvider", _FakeSahmkFundamentalProvider
    )
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60")
    yield
    fundamental_provider_factory.reset_fundamental_provider_cache()


@pytest.mark.asyncio
async def test_forced_dev_returns_dev_provider_even_with_credentials(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")
    provider = await fundamental_provider_factory.get_fundamental_data_provider()
    assert isinstance(provider, DevFundamentalDataProvider)


@pytest.mark.asyncio
async def test_auto_without_credentials_returns_dev_provider():
    provider = await fundamental_provider_factory.get_fundamental_data_provider()
    assert isinstance(provider, DevFundamentalDataProvider)


@pytest.mark.asyncio
async def test_auto_with_credentials_and_reachable_sahmk_returns_sahmk_provider(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkFundamentalProvider.authenticate = lambda self: _ok()

    provider = await fundamental_provider_factory.get_fundamental_data_provider()
    assert isinstance(provider, _FakeSahmkFundamentalProvider)
    assert fundamental_provider_factory.get_last_selected_fundamental_provider_kind() == "sahmk"


@pytest.mark.asyncio
async def test_auto_with_credentials_but_unreachable_host_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _network_error():
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    _FakeSahmkFundamentalProvider.authenticate = lambda self: _network_error()

    provider = await fundamental_provider_factory.get_fundamental_data_provider()
    assert isinstance(provider, DevFundamentalDataProvider)
    assert _FakeSahmkFundamentalProvider.instances[0].disconnected is True


@pytest.mark.asyncio
async def test_auto_with_credentials_probe_timeout_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _hangs():
        await asyncio.sleep(10)
        return True

    _FakeSahmkFundamentalProvider.authenticate = lambda self: _hangs()

    provider = await fundamental_provider_factory.get_fundamental_data_provider()
    assert isinstance(provider, DevFundamentalDataProvider)


@pytest.mark.asyncio
async def test_selection_is_cached_across_calls(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkFundamentalProvider.authenticate = lambda self: _ok()

    await fundamental_provider_factory.get_fundamental_data_provider()
    await fundamental_provider_factory.get_fundamental_data_provider()
    assert len(_FakeSahmkFundamentalProvider.instances) == 1
