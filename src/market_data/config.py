"""Environment-driven configuration for the SAHMK (sahmk.sa) market data
integration.

No secret ever has a default value here -- SAHMK_API_KEY must come from
the environment (.env locally, a real secret store in production).
SAHMK_BASE_URL's default is SAHMK's own published, public API base URL
-- not a secret -- and remains overridable for testing against a
different host.
"""

import os

SAHMK_DEFAULT_BASE_URL = "https://app.sahmk.sa/api/v1"


def get_sahmk_api_key() -> str:
    """Returns the configured SAHMK API key, or "" if unset.

    Never raises and never invents a value -- callers that require a key
    (SahmkClient) are responsible for deciding what "" means for them.
    """
    return os.getenv("SAHMK_API_KEY", "")


def get_sahmk_base_url() -> str:
    """Returns the configured SAHMK API base URL, defaulting to SAHMK's
    own published base URL if SAHMK_BASE_URL is unset."""
    return os.getenv("SAHMK_BASE_URL", SAHMK_DEFAULT_BASE_URL) or SAHMK_DEFAULT_BASE_URL


def has_sahmk_credentials() -> bool:
    """True iff a non-empty SAHMK_API_KEY is configured."""
    return bool(get_sahmk_api_key())


def get_configured_provider_name() -> str:
    """Returns the explicit MARKET_DATA_PROVIDER override, lower-cased,
    or "auto" if unset. "auto" means: let provider_factory decide based
    on credential presence and live connectivity, rather than a fixed
    choice."""
    return os.getenv("MARKET_DATA_PROVIDER", "auto").strip().lower() or "auto"


def get_provider_probe_timeout_seconds() -> float:
    """Timeout for the one-off connectivity probe provider_factory uses
    to decide whether SAHMK is actually reachable from this environment.
    Kept short and separate from SahmkClient's own per-request timeout so
    an unreachable host doesn't stall application startup."""
    return float(os.getenv("SAHMK_PROBE_TIMEOUT_SECONDS", "5"))


def get_provider_selection_cache_seconds() -> float:
    """How long provider_factory's auto-selection result is cached
    before re-probing connectivity. 0 disables caching (always re-probe)."""
    return float(os.getenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60"))
