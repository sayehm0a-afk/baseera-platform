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


class StaffAccountSelfDeletionError(APIError):
    """A staff account (`is_staff=True` -- SUPPORT/ADMIN/OWNER) tried to
    delete itself through the consumer self-service DELETE /auth/me
    route. Blocked outright: staff identities are operational/
    administrative, not customer accounts, and this route has no
    concept of "who else still holds OWNER" the way a deliberate staff
    off-boarding process would need to check -- an OWNER self-deleting
    here could leave the platform with zero OWNERs and no path back in
    (mirrors the same reasoning `CannotModifyOwnStaffRoleError`,
    src/admin/exceptions.py, already applies to the admin staff-role
    route). Revoking staff access is an admin action
    (`POST /api/v1/admin/users/{id}/staff-role`, OWNER-only) that must
    happen before this account could ever use this route."""

    status_code = 403
    code = "staff_account_self_deletion_blocked"


class OwnerBootstrapAlreadyCompleteError(APIError):
    """POST /api/v1/bootstrap/owner (src/api/routes/bootstrap.py) was
    called after an OWNER account already exists -- the route's
    self-disabling precondition, enforced by real DB state (not a flag
    that could be reset), permanently refuses every call after the
    first successful one."""

    status_code = 403
    code = "owner_bootstrap_already_complete"


class AccountHasBillingHistoryError(APIError):
    """Self-service DELETE /auth/me hit the same FK RESTRICT the admin
    hard-delete route (src/api/routes/admin/users.py) already surfaces
    as `user_has_related_records` -- a real invoice/payment/audit
    history exists for this account and must not be silently discarded.
    Distinct code/message (customer-facing: "contact support" rather
    than the admin-facing wording) for the same underlying condition."""

    status_code = 409
    code = "account_has_billing_history"
