"""Auth-layer exceptions -- same convention as src/api/exceptions.py:
each subclass just overrides `status_code`/`code`, and every instance
flows through the existing `register_error_handlers`/`api_error_handler`
machinery unchanged (no new error envelope shape).
"""

from src.api.exceptions import APIError


class EmailAlreadyRegisteredError(APIError):
    status_code = 409
    code = "email_already_registered"


class InvalidCredentialsError(APIError):
    status_code = 401
    code = "invalid_credentials"


class AccountLockedError(APIError):
    """Too many recent failed login attempts on this specific account
    (src/auth/user_service.py's failed_login_attempts/locked_until) --
    distinct from the per-IP rate limit on /auth/login
    (src/api/middleware/rate_limiting.py), which an attacker rotating
    IPs bypasses but this does not. Deliberately still fairly generic
    wording (never states *which* account or *how many* attempts) to
    keep the enumeration surface as small as this mechanism allows --
    see docs/AUTHENTICATION_SECURITY.md for the disclosed trade-off
    this still accepts (a locked-account response is itself
    distinguishable from a plain wrong-password response)."""

    status_code = 429
    code = "account_locked"


class EmailNotVerifiedError(APIError):
    status_code = 403
    code = "email_not_verified"


class AccountSuspendedError(APIError):
    status_code = 403
    code = "account_suspended"


class InvalidOrExpiredTokenError(APIError):
    """A verification/reset/refresh token was malformed, unknown,
    already consumed, or past its expiry -- a client-correctable 400,
    not a server failure."""

    status_code = 400
    code = "invalid_or_expired_token"


class UnauthenticatedError(APIError):
    """No valid access token was presented at all (missing/garbled
    cookie) -- distinct from InvalidCredentialsError (a login attempt
    with a wrong password)."""

    status_code = 401
    code = "unauthenticated"


class InsufficientPermissionError(APIError):
    status_code = 403
    code = "insufficient_permission"


class SessionNotFoundError(APIError):
    """No such device session, or it belongs to a different user --
    404 (not 403) so a caller can never distinguish "not yours" from
    "doesn't exist" and enumerate other users' session IDs."""

    status_code = 404
    code = "session_not_found"


class SubscriptionRequiredError(APIError):
    """No active (trialing/active) subscription -- 402 Payment
    Required, the semantically precise status for exactly this case,
    distinct from InsufficientPermissionError's 403 (a role/permission
    problem, not a billing one)."""

    status_code = 402
    code = "subscription_required"
