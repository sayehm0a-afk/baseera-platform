"""Market-data provider configuration, read from environment variables
at call time only (no import-time side effects) -- the same lazy-init
discipline src.core.db.database's engine and src.api.config already
follow.

No credential is ever hardcoded here or anywhere in this package: every
secret is an `os.getenv(...)` read, matching the existing, already-
established `TADAWUL_API_KEY`/`SECRET_KEY`/`API_KEY` pattern in
.env.example.

As of the SAHMK integration: `SAHMK_BASE_URL` defaults to SAHMK's own
publicly-documented base URL (`https://app.sahmk.sa/api/v1`, confirmed
via https://github.com/sahmk-sa/sahmk-python -- see
docs/SAHMK_INTEGRATION.md). That default is not a secret -- it is the
same public value SAHMK publishes in their own SDK -- so defaulting it
(while still allowing an env override for a staging/alternate endpoint)
is safe. `SAHMK_API_KEY` has no default; it must always come from the
environment.
"""

import os

_SAHMK_DEFAULT_BASE_URL = "https://app.sahmk.sa/api/v1"


def get_configured_provider_name() -> str:
    """Which provider `get_configured_provider()`
    (provider_factory.py) should build. Defaults to "dev" (the
    synthetic provider) -- a missing/unset MARKET_DATA_PROVIDER must
    never silently attempt a live call with no real credentials
    configured."""
    return os.getenv("MARKET_DATA_PROVIDER", "dev")


def is_live_data_enabled() -> bool:
    """Explicit kill switch, independent of MARKET_DATA_PROVIDER: even
    if MARKET_DATA_PROVIDER=sahmk is set, provider_factory refuses to
    construct a live provider unless this is also "true" -- a second,
    deliberate step required to go live, per Secure-by-Default. Defaults
    to False."""
    return os.getenv("SAHMK_LIVE_DATA_ENABLED", "false").strip().lower() == "true"


def get_sahmk_api_key() -> str:
    return os.getenv("SAHMK_API_KEY", "")


def get_sahmk_base_url() -> str:
    return os.getenv("SAHMK_BASE_URL", _SAHMK_DEFAULT_BASE_URL)


def get_provider_max_retries() -> int:
    return int(os.getenv("MARKET_DATA_MAX_RETRIES", 3))


def get_provider_timeout_seconds() -> int:
    return int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", 30))


def get_circuit_breaker_failure_threshold() -> int:
    return int(os.getenv("MARKET_DATA_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3))


def get_circuit_breaker_recovery_timeout_seconds() -> int:
    return int(os.getenv("MARKET_DATA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", 30))


def get_quote_cache_ttl_seconds() -> float:
    """Short TTL -- quotes/index snapshots change through the trading
    day (Phase 5's "الأسعار الحالية: مدة قصيرة")."""
    return float(os.getenv("MARKET_DATA_QUOTE_CACHE_TTL_SECONDS", 60.0))


def get_historical_cache_ttl_seconds() -> float:
    """Long TTL -- a past date's OHLCV bar never changes once the
    trading day has closed (Phase 5's "البيانات التاريخية: مدة أطول")."""
    return float(os.getenv("MARKET_DATA_HISTORICAL_CACHE_TTL_SECONDS", 3600.0))
