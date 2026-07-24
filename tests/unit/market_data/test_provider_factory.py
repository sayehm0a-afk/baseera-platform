"""Unit tests for get_configured_provider() -- selection is driven
entirely by the MARKET_DATA_PROVIDER environment variable, never a
hardcoded default other than "dev" when unset/unknown."""

from src.market_data.provider_factory import get_configured_provider
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.sahmak_market_data_provider import SahmakMarketDataProvider


def test_defaults_to_dev_provider_when_unset(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_selects_dev_provider_explicitly(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_selects_sahmak_provider(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmak")
    provider = get_configured_provider()
    assert isinstance(provider, SahmakMarketDataProvider)


def test_unknown_provider_name_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "nonexistent-vendor")
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_sahmak_provider_reads_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmak")
    monkeypatch.setenv("SAHMAK_API_KEY", "k")
    monkeypatch.setenv("SAHMAK_BASE_URL", "https://env.example.invalid")

    provider = get_configured_provider()

    assert provider.api_key == "k"
    assert provider.api_endpoint == "https://env.example.invalid"
