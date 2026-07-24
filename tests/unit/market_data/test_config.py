"""Unit tests for src.market_data.config -- every getter reads its
environment variable lazily (at call time), never at import time, and
falls back to a documented default when unset."""

from src.market_data import config


def test_get_configured_provider_name_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    assert config.get_configured_provider_name() == "dev"


def test_get_configured_provider_name_reads_env(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    assert config.get_configured_provider_name() == "sahmk"


def test_is_live_data_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("SAHMK_LIVE_DATA_ENABLED", raising=False)
    assert config.is_live_data_enabled() is False


def test_is_live_data_enabled_true_only_for_exact_true_string(monkeypatch):
    for value, expected in [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("1", False),
        ("yes", False),
        ("", False),
    ]:
        monkeypatch.setenv("SAHMK_LIVE_DATA_ENABLED", value)
        assert config.is_live_data_enabled() is expected, value


def test_sahmk_api_key_defaults_to_empty_string(monkeypatch):
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    assert config.get_sahmk_api_key() == ""


def test_sahmk_api_key_reads_from_env(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "k")
    assert config.get_sahmk_api_key() == "k"


def test_sahmk_base_url_defaults_to_documented_public_endpoint(monkeypatch):
    monkeypatch.delenv("SAHMK_BASE_URL", raising=False)
    assert config.get_sahmk_base_url() == "https://app.sahmk.sa/api/v1"


def test_sahmk_base_url_reads_from_env_override(monkeypatch):
    monkeypatch.setenv("SAHMK_BASE_URL", "https://staging.example.invalid")
    assert config.get_sahmk_base_url() == "https://staging.example.invalid"


def test_numeric_tunables_have_documented_defaults(monkeypatch):
    for var in (
        "MARKET_DATA_MAX_RETRIES",
        "MARKET_DATA_TIMEOUT_SECONDS",
        "MARKET_DATA_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        "MARKET_DATA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS",
        "MARKET_DATA_QUOTE_CACHE_TTL_SECONDS",
        "MARKET_DATA_HISTORICAL_CACHE_TTL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    assert config.get_provider_max_retries() == 3
    assert config.get_provider_timeout_seconds() == 30
    assert config.get_circuit_breaker_failure_threshold() == 3
    assert config.get_circuit_breaker_recovery_timeout_seconds() == 30
    assert config.get_quote_cache_ttl_seconds() == 60.0
    assert config.get_historical_cache_ttl_seconds() == 3600.0


def test_numeric_tunables_read_from_env(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_MAX_RETRIES", "5")
    monkeypatch.setenv("MARKET_DATA_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("MARKET_DATA_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "7")
    monkeypatch.setenv("MARKET_DATA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("MARKET_DATA_QUOTE_CACHE_TTL_SECONDS", "12.5")
    monkeypatch.setenv("MARKET_DATA_HISTORICAL_CACHE_TTL_SECONDS", "7200")

    assert config.get_provider_max_retries() == 5
    assert config.get_provider_timeout_seconds() == 45
    assert config.get_circuit_breaker_failure_threshold() == 7
    assert config.get_circuit_breaker_recovery_timeout_seconds() == 90
    assert config.get_quote_cache_ttl_seconds() == 12.5
    assert config.get_historical_cache_ttl_seconds() == 7200.0
