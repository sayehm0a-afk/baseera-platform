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


class SahmkResponseValidationError(SahmkError):
    """The response was a 2xx but did not contain the fields this
    integration requires -- never fabricated, always raised instead."""


class SahmkRequestError(SahmkError):
    """Any other non-2xx response, or a network-level failure (after
    retries), not covered by the more specific exceptions above."""
