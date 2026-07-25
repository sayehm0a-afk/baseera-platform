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
