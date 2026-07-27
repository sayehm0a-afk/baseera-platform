"""Unit tests for src.market_data.config -- env var parsing only, no I/O."""

from src.market_data import config as market_data_config


def test_get_sahmk_api_key_defaults_to_empty_string(monkeypatch):
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    assert market_data_config.get_sahmk_api_key() == ""


def test_get_sahmk_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_test_abc123")
    assert market_data_config.get_sahmk_api_key() == "shmk_test_abc123"


def test_no_hardcoded_api_key_default():
    """The whole point of reading from the environment: the module
    itself must never contain a usable-looking key literal."""
    import inspect

    source = inspect.getsource(market_data_config)
    assert "shmk_" not in source


def test_get_sahmk_base_url_defaults_to_published_url(monkeypatch):
    monkeypatch.delenv("SAHMK_BASE_URL", raising=False)
    assert market_data_config.get_sahmk_base_url() == market_data_config.SAHMK_DEFAULT_BASE_URL


def test_get_sahmk_base_url_reads_env_override(monkeypatch):
    monkeypatch.setenv("SAHMK_BASE_URL", "https://sahmk.example.invalid/api/v1")
    assert market_data_config.get_sahmk_base_url() == "https://sahmk.example.invalid/api/v1"


def test_get_sahmk_base_url_falls_back_on_empty_env(monkeypatch):
    monkeypatch.setenv("SAHMK_BASE_URL", "")
    assert market_data_config.get_sahmk_base_url() == market_data_config.SAHMK_DEFAULT_BASE_URL


def test_has_sahmk_credentials_reflects_key_presence(monkeypatch):
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    assert market_data_config.has_sahmk_credentials() is False
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")
    assert market_data_config.has_sahmk_credentials() is True


def test_get_configured_provider_name_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    assert market_data_config.get_configured_provider_name() == "auto"


def test_get_configured_provider_name_normalizes_case(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", " SAHMK ")
    assert market_data_config.get_configured_provider_name() == "sahmk"


def test_get_provider_probe_timeout_seconds_defaults_and_reads_env(monkeypatch):
    monkeypatch.delenv("SAHMK_PROBE_TIMEOUT_SECONDS", raising=False)
    assert market_data_config.get_provider_probe_timeout_seconds() == 5.0
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "2.5")
    assert market_data_config.get_provider_probe_timeout_seconds() == 2.5


def test_get_provider_selection_cache_seconds_defaults_and_reads_env(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", raising=False)
    assert market_data_config.get_provider_selection_cache_seconds() == 60.0
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "0")
    assert market_data_config.get_provider_selection_cache_seconds() == 0.0
