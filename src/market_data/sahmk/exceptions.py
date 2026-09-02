"""Exception hierarchy for the SAHMK (sahmk.sa) integration.

Mirrors SAHMK's confirmed REST error semantics (see
docs/SAHMK_INTEGRATION.md): a 403 with body ``PLAN_LIMIT`` is a
confirmed, distinct condition from a 401; a 429 is retried internally by
SahmkClient and only ever raised as SahmkRateLimitError if every retry
is exhausted. Every exception here carries the raw response body (when
available) so nothing is silently swallowed.

Raw-provider-evidence observability fix: `self.body` was always
captured here, but every caller that persisted a failure (most notably
ingest_historical_ohlcv.py) stored only `str(exc)` -- which, because
`SahmkError.__init__` calls `super().__init__(message)` with just the
fixed message, never included `body` at all. A real 2026-08-31 Historical
OHLCV production incident (49/49 symbols failing with a generic "SAHMK
plan does not permit this endpoint (403 PLAN_LIMIT)" message) could not
be root-caused from persisted evidence as a direct result: the actual
upstream response body was discarded the instant the exception was
caught. `sanitized_provider_detail()` below is the fix -- a bounded,
defensively-redacted string form of `self.body` that callers can persist
*alongside* the existing message, without changing `str(exc)` itself (so
every existing caller/test that depends on the current message shape is
unaffected)."""

import json
import re
from typing import Any, Optional

# Generous enough to hold a real SAHMK JSON error body in full (the
# largest observed, `docs/SAHMK_INTEGRATION.md`'s quoted bodies, are a
# few hundred characters), small enough that a pathological/oversized
# body can never bloat a persisted IngestionRunLog.error_summary row.
_MAX_PROVIDER_DETAIL_CHARS = 2000

# Defense-in-depth only: `body` is SAHMK's own response, never our own
# request, so it structurally cannot contain our API key -- but a
# malformed/unexpected upstream payload (or a misbehaving intermediary)
# echoing something key-shaped back is exactly the scenario this exists
# to catch before it ever reaches a log or database row. Two passes:
# "Bearer <token>" first (its own token immediately follows the
# keyword, not a "key: value" shape), then every other label ("X-API-
# Key: ...", "secret=...") -- run in this order so a value that itself
# starts with "Bearer " (the common Authorization-header shape) has its
# real token redacted, not just the word "Bearer".
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bbearer\s+\S+")
_SENSITIVE_KEY_VALUE_PATTERN = re.compile(
    r'(?i)\b(api[_-]?key|x-api-key|authorization|cookie|secret|token)\b("?\s*[:=]\s*"?)([^\s"\',}]+)'
)


def _redact_sensitive(text: str) -> str:
    text = _BEARER_TOKEN_PATTERN.sub("bearer [REDACTED]", text)
    text = _SENSITIVE_KEY_VALUE_PATTERN.sub(r"\1\2[REDACTED]", text)
    return text


class SahmkError(Exception):
    """Base class for every SAHMK-integration-specific error."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body

    def sanitized_provider_detail(self) -> str:
        """A safe, size-bounded, redacted string form of the real
        upstream `body` this exception carries -- "" if none was
        captured (e.g. a network-level failure with no HTTP response
        at all). Deliberately NOT part of `__str__`/`str(exc)`, which
        keeps its existing, stable, test-verified shape -- callers that
        want the real provider evidence call this explicitly."""
        if self.body is None:
            return ""
        if isinstance(self.body, (dict, list)):
            try:
                text = json.dumps(self.body, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError):
                text = str(self.body)
        else:
            text = str(self.body)
        text = _redact_sensitive(text)
        if len(text) > _MAX_PROVIDER_DETAIL_CHARS:
            text = text[:_MAX_PROVIDER_DETAIL_CHARS] + "...<truncated>"
        return text


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
