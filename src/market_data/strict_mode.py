"""Strict real-data mode's exception: the production guarantee that
Basirah never silently substitutes synthetic/development data for real
SAHMK data.

`StrictRealDataUnavailableError` is deliberately NOT a `SahmkError`
subclass. `SahmkError` is caught broadly throughout this codebase
(context_builder.py's per-leg degradation, provider_factory.py's own
internal connectivity probe, etc.) precisely so a real SAHMK outage
degrades a single leg gracefully instead of crashing a whole request.
This exception must do the opposite of that: propagate through every
one of those handlers unmodified and stop the caller, because
"degrade gracefully by substituting something else" is exactly the
silent-fallback behavior strict mode exists to forbid. Subclassing
`RuntimeError` instead guarantees it is never accidentally absorbed by
an `except SahmkError` (or `except (SahmkError, CircuitBreakerOpenError)`)
block anywhere in the codebase.
"""


class StrictRealDataUnavailableError(RuntimeError):
    """Raised in place of a synthetic-data fallback when
    STRICT_REAL_DATA=true (or ALLOW_SYNTHETIC_DATA=false) and real
    SAHMK data cannot be obtained -- missing/invalid/unauthorized/
    rate-limited credentials, or SAHMK being unreachable. `reason` is
    always a plain operational description; never includes the API
    key or any other secret value."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
