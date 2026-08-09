"""Environment-driven configuration for the SAHMK (sahmk.sa) market data
integration.

No secret ever has a default value here -- SAHMK_API_KEY must come from
the environment (.env locally, a real secret store in production).
SAHMK_BASE_URL's default is SAHMK's own published, public API base URL
-- not a secret -- and remains overridable for testing against a
different host.
"""

import os
from typing import Optional

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


def get_provider_probe_max_attempts() -> int:
    """How many times provider_factory/fundamental_provider_factory retry
    the connectivity probe (SahmkMarketDataProvider/
    SahmkFundamentalDataProvider.check_connectivity()) on a transient
    failure (probe timeout, an exhausted-but-recoverable 429, a
    network-error-shaped SahmkRequestError) before giving up. Never
    retries a deterministic permanent outcome (401, 403 is already
    "authenticated", missing key, an open circuit breaker) regardless
    of this value -- see provider_connectivity_retry.py.

    Production evidence (2026-08-08): the fundamentals ingestion job
    failed twice in a row with "SAHMK connectivity probe timed out"
    immediately after the multi-minute historical_ohlcv job -- the
    probe's own single asyncio.wait_for(..., timeout=
    SAHMK_PROBE_TIMEOUT_SECONDS) had no retry of its own, so one slow
    response right after a burst of prior SAHMK traffic was enough to
    raise StrictRealDataUnavailableError with zero retries at this
    layer, even though SahmkClient's own per-request retry (3 attempts)
    never got the chance to run to completion."""
    return int(os.getenv("SAHMK_PROBE_MAX_ATTEMPTS", "3"))


def get_provider_probe_retry_base_delay_seconds() -> float:
    """Base delay for the connectivity probe's exponential-backoff-with-
    full-jitter retry (see provider_connectivity_retry._backoff_delay).
    Attempt N waits a random value in [0, min(base * 2**(N-1), max)]."""
    return float(os.getenv("SAHMK_PROBE_RETRY_BASE_DELAY_SECONDS", "1.0"))


def get_provider_probe_retry_max_delay_seconds() -> float:
    """Ceiling on any single connectivity-probe retry delay, including
    one derived from a 429's Retry-After header -- a misbehaving or
    unusually large Retry-After must never stall provider selection
    for an unbounded time."""
    return float(os.getenv("SAHMK_PROBE_RETRY_MAX_DELAY_SECONDS", "8.0"))


def get_provider_selection_cache_seconds() -> float:
    """How long provider_factory's auto-selection result is cached
    before re-probing connectivity. 0 disables caching (always re-probe)."""
    return float(os.getenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60"))


def get_provider_disconnect_grace_seconds() -> float:
    """How long provider_factory/fundamental_provider_factory keep a
    superseded provider's session open before actually closing it, once
    a genuine kind change (sahmk <-> dev) supersedes it. Must comfortably
    exceed both a single SAHMK request's own timeout and the SAHMK rate
    limiter's worst-case per-minute wait, so a caller still mid-loop
    against the superseded provider isn't cut off. See
    provider_factory._disconnect_with_grace()'s docstring for the
    concurrency bug this guards against."""
    return float(os.getenv("MARKET_DATA_PROVIDER_DISCONNECT_GRACE_SECONDS", "90"))


def get_sahmk_max_requests_per_minute() -> int:
    """Ceiling on SAHMK requests per rolling 60s window, shared by every
    SahmkClient in this process (src.market_data.sahmk.rate_limiter) --
    SAHMK's quota is per API key, not per client instance. The exact
    Starter-plan number is unverified (see docs/SAHMK_INTEGRATION.md);
    20/minute is a deliberately conservative default, not a confirmed
    quota -- override with the real number once known."""
    return int(os.getenv("SAHMK_MAX_REQUESTS_PER_MINUTE", "20"))


def is_strict_real_data_enabled() -> bool:
    """True iff STRICT_REAL_DATA=true. Strict real-data mode is
    Basirah's production guarantee that it never analyzes or publishes
    synthetic/development data as if it were the real Saudi market:
    provider_factory/fundamental_provider_factory raise instead of
    silently substituting DevMarketDataProvider/DevFundamentalDataProvider
    whenever real SAHMK data cannot be obtained. Off by default so
    every existing dev/CI/test flow is completely unaffected unless a
    deployment explicitly opts in."""
    return os.getenv("STRICT_REAL_DATA", "false").strip().lower() in ("true", "1", "yes")


def is_synthetic_data_allowed() -> bool:
    """False whenever synthetic (Dev-provider) data must never be used
    -- either because ALLOW_SYNTHETIC_DATA=false is set explicitly, or
    because STRICT_REAL_DATA=true (which implies it; strict mode is
    the stronger, absolute switch and cannot be re-permitted by a
    separately-set ALLOW_SYNTHETIC_DATA=true). True otherwise -- the
    existing, unaffected default for dev/CI/test."""
    if is_strict_real_data_enabled():
        return False
    raw = os.getenv("ALLOW_SYNTHETIC_DATA")
    if raw is None:
        return True
    return raw.strip().lower() not in ("false", "0", "no")


def get_sahmk_max_requests_per_day() -> Optional[int]:
    """Calendar-day (UTC) request quota, enforced client-side by
    SahmkRateLimiter so a spent quota fails fast locally (an ingestion
    job sees SahmkRateLimitExceededError immediately) instead of
    silently spending real requests to discover a 429, or -- worse --
    a retry storm hammering an already-exhausted quota (see
    src.market_data.sahmk.client's tenacity retry, which retries a 429
    up to 3x per logical call with no awareness this is a quota, not a
    transient failure).

    Confirmed real account limit (2026-08-09 production evidence, from
    SAHMK's own 429 body: "Daily rate limit exceeded (5000 requests/day)")
    is 5000/day. Default here is 4500, not 5000 -- deliberate headroom
    for: (a) this being a per-process counter (see rate_limiter.py's
    module docstring -- a second process/worker/replica has its own
    independent 4500 budget, so the true cross-process ceiling can only
    be bounded, not hit exactly, without a shared Redis-backed counter,
    which is a disclosed, not-yet-built limitation); (b) any request
    made through a channel this limiter doesn't see (e.g. a manual
    curl against the API using the same key, outside this application
    entirely). Override with SAHMK_MAX_REQUESTS_PER_DAY once a
    Redis-backed cross-process counter exists and/or the plan's true
    quota is reconfirmed; set to "" (empty string) to disable the
    client-side cap entirely and rely on SAHMK's own 429 only, as
    before this default existed."""
    raw = os.getenv("SAHMK_MAX_REQUESTS_PER_DAY", "4500")
    return int(raw) if raw.strip() else None


def get_sahmk_reserved_for_critical_requests_per_day() -> Optional[int]:
    """How many of get_sahmk_max_requests_per_day()'s requests are
    reserved for priority=CRITICAL callers only (live Decision
    Engine / market-scan quote lookups -- see
    src.market_data.sahmk.request_priority) once background work
    (ingestion backfills, admin diagnostics) has used up the rest.
    None (the default when SAHMK_MAX_REQUESTS_PER_DAY is unset,
    disabling the daily cap entirely) or 0 disables the reservation --
    background and critical work then draw from the same undivided
    daily budget, exactly as before this mechanism existed. Default
    1000 (of the default 4500/day budget): sized to comfortably cover
    one full market-scan cycle of the current ~384-symbol active
    universe (1 request/symbol, see docs/SAHMK_INTEGRATION.md's
    request-budget model) even on a day background jobs have already
    spent the rest."""
    raw = os.getenv("SAHMK_RESERVED_FOR_CRITICAL_REQUESTS_PER_DAY", "1000")
    if not raw.strip():
        return None
    value = int(raw)
    return value if value > 0 else None
