"""Market-data provider configuration, read from environment variables
at call time only (no import-time side effects) -- the same lazy-init
discipline src.core.db.database's engine and src.api.config already
follow.

No credential is ever hardcoded here or anywhere in this package: every
secret is an `os.getenv(...)` read, matching the existing, already-
established `TADAWUL_API_KEY`/`SECRET_KEY`/`API_KEY` pattern in
.env.example.
"""

import os


def get_configured_provider_name() -> str:
    """Which provider `get_configured_provider()`
    (provider_factory.py) should build. Defaults to "dev" (the
    synthetic provider) -- a missing/unset MARKET_DATA_PROVIDER must
    never silently attempt a live call with no real credentials
    configured."""
    return os.getenv("MARKET_DATA_PROVIDER", "dev")


def get_sahmak_api_key() -> str:
    return os.getenv("SAHMAK_API_KEY", "")


def get_sahmak_api_secret() -> str:
    return os.getenv("SAHMAK_API_SECRET", "")


def get_sahmak_base_url() -> str:
    return os.getenv("SAHMAK_BASE_URL", "")


def get_provider_max_retries() -> int:
    return int(os.getenv("MARKET_DATA_MAX_RETRIES", 3))


def get_provider_timeout_seconds() -> int:
    return int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", 30))


def get_circuit_breaker_failure_threshold() -> int:
    return int(os.getenv("MARKET_DATA_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3))


def get_circuit_breaker_recovery_timeout_seconds() -> int:
    return int(os.getenv("MARKET_DATA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", 30))


def get_quote_cache_ttl_seconds() -> float:
    return float(os.getenv("MARKET_DATA_QUOTE_CACHE_TTL_SECONDS", 60.0))
