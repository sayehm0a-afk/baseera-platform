"""Unit tests for get_configured_provider() -- selection is driven
entirely by the MARKET_DATA_PROVIDER environment variable, never a
hardcoded default other than "dev" when unset/unknown, and gated by the
separate SAHMK_LIVE_DATA_ENABLED kill switch before a live provider is
ever actually constructed."""

from src.market_data.provider_factory import get_configured_provider
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider


def test_defaults_to_dev_provider_when_unset(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_selects_dev_provider_explicitly(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_selects_sahmk_provider_only_when_live_data_enabled(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    monkeypatch.setenv("SAHMK_LIVE_DATA_ENABLED", "true")
    provider = get_configured_provider()
    assert isinstance(provider, SahmkMarketDataProvider)


def test_sahmk_provider_name_without_live_flag_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    monkeypatch.delenv("SAHMK_LIVE_DATA_ENABLED", raising=False)
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_sahmk_provider_name_with_live_flag_false_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    monkeypatch.setenv("SAHMK_LIVE_DATA_ENABLED", "false")
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_unknown_provider_name_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "nonexistent-vendor")
    provider = get_configured_provider()
    assert isinstance(provider, DevMarketDataProvider)


def test_sahmk_provider_reads_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    monkeypatch.setenv("SAHMK_LIVE_DATA_ENABLED", "true")
    monkeypatch.setenv("SAHMK_API_KEY", "k")
    monkeypatch.setenv("SAHMK_BASE_URL", "https://env.example.invalid")

    provider = get_configured_provider()

    assert provider.api_key == "k"
    assert provider.api_endpoint == "https://env.example.invalid"
