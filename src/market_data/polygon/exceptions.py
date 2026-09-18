"""Exception hierarchy for the Polygon.io (US market data) integration.

Mirrors src.market_data.sahmk.exceptions's structure and its
`sanitized_provider_detail()` raw-provider-evidence observability fix
exactly (see that module's docstring for the full incident/rationale
this pattern exists to prevent) -- every exception here carries the
raw response body (when available) so a real Polygon failure can
always be root-caused from persisted evidence, with the same
size-bounded, credential-redacted string form available via
`sanitized_provider_detail()`. `str(exc)` itself stays unchanged by
that method, exactly like SahmkError.
"""

import json
import re
from typing import Any, Optional

# Same rationale/sizing as sahmk/exceptions.py's identical constant --
# generous enough for a real Polygon JSON error body in full, small
# enough that a pathological/oversized body can never bloat a
# persisted log row.
_MAX_PROVIDER_DETAIL_CHARS = 2000

# Defense-in-depth only, same reasoning as sahmk/exceptions.py: `body`
# is Polygon's own response, never our own request, so it structurally
# cannot contain our API key -- but a malformed/unexpected upstream
# payload (or a misbehaving intermediary) echoing something key-shaped
# back is exactly the scenario this exists to catch before it ever
# reaches a log or database row.
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bbearer\s+\S+")
_SENSITIVE_KEY_VALUE_PATTERN = re.compile(
    r'(?i)\b(api[_-]?key|x-api-key|authorization|cookie|secret|token)\b("?\s*[:=]\s*"?)([^\s"\',}]+)'
)


def _redact_sensitive(text: str) -> str:
    text = _BEARER_TOKEN_PATTERN.sub("bearer [REDACTED]", text)
    text = _SENSITIVE_KEY_VALUE_PATTERN.sub(r"\1\2[REDACTED]", text)
    return text


class PolygonError(Exception):
    """Base class for every Polygon-integration-specific error."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body

    def sanitized_provider_detail(self) -> str:
        """A safe, size-bounded, redacted string form of the real
        upstream `body` this exception carries -- "" if none was
        captured (e.g. a network-level failure with no HTTP response
        at all). Deliberately NOT part of `__str__`/`str(exc)`, which
        keeps its existing, stable shape -- callers that want the real
        provider evidence call this explicitly. Mirrors
        SahmkError.sanitized_provider_detail() exactly."""
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


class PolygonConfigurationError(PolygonError):
    """Raised when PolygonClient is used without a configured API key."""


class PolygonAuthenticationError(PolygonError):
    """The API key was rejected -- Polygon returns 401 for a missing/
    invalid key and 403 for a key that is valid but not entitled to the
    requested endpoint/plan; both are treated as this same, single
    authentication-shaped outcome since neither is a business response
    a caller can usefully act on differently."""


class PolygonRateLimitError(PolygonError):
    """Every retry attempt (default 3, honoring a 429's Retry-After
    header) was exhausted on a 429 response."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class PolygonResponseValidationError(PolygonError):
    """The response was a 2xx but did not contain the fields this
    integration requires -- never fabricated, always raised instead."""


class PolygonRequestError(PolygonError):
    """Any other non-2xx response, or a network-level failure (after
    retries), not covered by the more specific exceptions above."""
