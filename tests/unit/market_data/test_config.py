"""Unit tests for src.market_data.config -- every getter reads its
environment variable lazily (at call time), never at import time, and
falls back to a documented default when unset."""

from src.market_data import config


def test_get_configured_provider_name_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    assert config.get_configured_provider_name() == "dev"


def test_get_configured_provider_name_reads_env(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmak")
    assert config.get_configured_provider_name() == "sahmak"


def test_sahmak_credentials_default_to_empty_string(monkeypatch):
    monkeypatch.delenv("SAHMAK_API_KEY", raising=False)
    monkeypatch.delenv("SAHMAK_API_SECRET", raising=False)
    monkeypatch.delenv("SAHMAK_BASE_URL", raising=False)
    assert config.get_sahmak_api_key() == ""
    assert config.get_sahmak_api_secret() == ""
    assert config.get_sahmak_base_url() == ""


def test_sahmak_credentials_read_from_env(monkeypatch):
    monkeypatch.setenv("SAHMAK_API_KEY", "k")
    monkeypatch.setenv("SAHMAK_API_SECRET", "s")
    monkeypatch.setenv("SAHMAK_BASE_URL", "https://example.invalid")
    assert config.get_sahmak_api_key() == "k"
    assert config.get_sahmak_api_secret() == "s"
    assert config.get_sahmak_base_url() == "https://example.invalid"


def test_numeric_tunables_have_documented_defaults(monkeypatch):
    for var in (
        "MARKET_DATA_MAX_RETRIES",
        "MARKET_DATA_TIMEOUT_SECONDS",
        "MARKET_DATA_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        "MARKET_DATA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS",
        "MARKET_DATA_QUOTE_CACHE_TTL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    assert config.get_provider_max_retries() == 3
    assert config.get_provider_timeout_seconds() == 30
    assert config.get_circuit_breaker_failure_threshold() == 3
    assert config.get_circuit_breaker_recovery_timeout_seconds() == 30
    assert config.get_quote_cache_ttl_seconds() == 60.0


def test_numeric_tunables_read_from_env(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_MAX_RETRIES", "5")
    monkeypatch.setenv("MARKET_DATA_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("MARKET_DATA_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "7")
    monkeypatch.setenv("MARKET_DATA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("MARKET_DATA_QUOTE_CACHE_TTL_SECONDS", "12.5")

    assert config.get_provider_max_retries() == 5
    assert config.get_provider_timeout_seconds() == 45
    assert config.get_circuit_breaker_failure_threshold() == 7
    assert config.get_circuit_breaker_recovery_timeout_seconds() == 90
    assert config.get_quote_cache_ttl_seconds() == 12.5
