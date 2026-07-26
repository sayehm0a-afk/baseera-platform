"""Unit tests for src.core.config.settings.Settings -- the fail-fast
production-secret guarantee and basic env-var parsing. Instantiates
`Settings()` directly (not the cached `get_settings()`/`settings`
singleton) so each test observes a fresh read of the environment.
"""

import pytest

from src.core.config.settings import _DEV_INSECURE_SECRET_KEY, Settings


def test_defaults_are_development_and_insecure_dev_secret(monkeypatch):
    monkeypatch.delenv("BASEERA_ENV", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.is_production is False
    assert settings.secret_key == _DEV_INSECURE_SECRET_KEY


def test_production_with_dev_secret_raises(monkeypatch):
    monkeypatch.setenv("BASEERA_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_production_with_real_secret_succeeds(monkeypatch):
    monkeypatch.setenv("BASEERA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-real-unique-production-secret")

    settings = Settings(_env_file=None)
    assert settings.is_production is True
    assert settings.secret_key == "a-real-unique-production-secret"


def test_invalid_environment_value_rejected(monkeypatch):
    monkeypatch.setenv("BASEERA_ENV", "not-a-real-environment")

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_cors_allowed_origins_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.baseerah.sa, https://staging.baseerah.sa")

    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == ["https://app.baseerah.sa", "https://staging.baseerah.sa"]


def test_cors_allowed_origins_defaults_to_empty_list(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == []


def test_trusted_hosts_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv("TRUSTED_HOSTS", "app.baseerah.sa, api.baseerah.sa")

    settings = Settings(_env_file=None)
    assert settings.trusted_hosts == ["app.baseerah.sa", "api.baseerah.sa"]


def test_trusted_hosts_defaults_to_empty_list(monkeypatch):
    monkeypatch.delenv("TRUSTED_HOSTS", raising=False)

    settings = Settings(_env_file=None)
    assert settings.trusted_hosts == []


def test_redis_dsn_prefers_explicit_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "rediss://:secret@managed-redis.example.com:6380/0")
    monkeypatch.setenv("REDIS_HOST", "should-be-ignored")

    settings = Settings(_env_file=None)
    assert settings.redis_dsn == "rediss://:secret@managed-redis.example.com:6380/0"


def test_redis_dsn_assembles_from_host_port_when_no_url_or_password(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")

    settings = Settings(_env_file=None)
    assert settings.redis_dsn == "redis://localhost:6379/0"


def test_redis_dsn_includes_password_when_set_without_a_full_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis.internal")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_PASSWORD", "hunter2")

    settings = Settings(_env_file=None)
    assert settings.redis_dsn == "redis://:hunter2@redis.internal:6379/0"
