"""Exception hierarchy for the SAHMK (sahmk.sa) integration.

Mirrors SAHMK's confirmed REST error semantics (see
docs/SAHMK_INTEGRATION.md): a 403 with body ``PLAN_LIMIT`` is a
confirmed, distinct condition from a 401; a 429 is retried internally by
SahmkClient and only ever raised as SahmkRateLimitError if every retry
is exhausted. Every exception here carries the raw response body (when
available) so nothing is silently swallowed.
"""

from typing import Any, Optional


class SahmkError(Exception):
    """Base class for every SAHMK-integration-specific error."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class SahmkConfigurationError(SahmkError):
    """Raised when SahmkClient is used without a configured API key."""


class SahmkAuthenticationError(SahmkError):
    """The API key was rejected (REST 401 -- see docs/SAHMK_INTEGRATION.md
    "Known gaps": the exact status code is unverified against a live
    account, treated defensively as 401)."""


class SahmkEntitlementError(SahmkError):
    """Confirmed REST 403 with body ``PLAN_LIMIT`` -- the key is valid but
    the current plan does not permit the requested endpoint."""


class SahmkRateLimitError(SahmkError):
    """Every retry attempt (default 3, honoring ``Retry-After``) was
    exhausted on a 429 response."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class SahmkDailyQuotaExhaustedError(SahmkRateLimitError):
    """A 429 whose response body was recognized as SAHMK's real,
    evidence-based *daily* quota exhaustion (e.g. "Daily rate limit
    exceeded (5000 requests/day)... Expected available in N seconds"),
    as opposed to a short-lived per-second/per-minute burst 429.

    2026-08-10 production evidence: SahmkRateLimiter's own local daily
    counter (UTC-midnight reset) can show a healthy remaining budget
    while SAHMK's real account-wide quota is already exhausted for
    several more hours -- the local counter is only ever an optimistic
    estimate, never authoritative. This distinct exception type is
    what lets callers (provider_connectivity_retry.py's retry
    wrapper, SahmkRateLimiter.record_upstream_daily_exhaustion) treat
    "SAHMK told us, in its own words, that today's quota is spent"
    completely differently from a transient rate limit: never retried
    (retrying a multi-hour exhaustion within a few seconds of backoff
    is pure waste), and recorded as the current real-world quota truth
    so every other request/worker/process stops hammering SAHMK until
    the evidence-based reset time SAHMK itself reported, not a
    guessed one.
    """

    def __init__(self, message: str, *, retry_after_seconds: Optional[float] = None, **kwargs):
        super().__init__(message, retry_after=retry_after_seconds, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class SahmkResponseValidationError(SahmkError):
    """The response was a 2xx but did not contain the fields this
    integration requires -- never fabricated, always raised instead."""


class SahmkRequestError(SahmkError):
    """Any other non-2xx response, or a network-level failure (after
    retries), not covered by the more specific exceptions above."""
