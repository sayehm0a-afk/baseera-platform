"""Admin-layer exceptions -- same convention as src/api/exceptions.py:
each subclass just overrides `status_code`/`code`, and every instance
flows through the existing `register_error_handlers`/`api_error_handler`
machinery unchanged.
"""

from src.api.exceptions import APIError


class AdminUserNotFoundError(APIError):
    status_code = 404
    code = "user_not_found"


class UserHasRelatedRecordsError(APIError):
    """Raised when an admin tries to hard-delete a user who has real
    financial/audit history (invoices, audit log entries as actor,
    etc.) -- the database's own foreign-key RESTRICT correctly blocks
    this; suspending the account is the right action instead."""

    status_code = 409
    code = "user_has_related_records"


class AdminSubscriptionNotFoundError(APIError):
    status_code = 404
    code = "subscription_not_found"


class FeatureFlagNotFoundError(APIError):
    status_code = 404
    code = "feature_flag_not_found"


class FeatureFlagAlreadyExistsError(APIError):
    status_code = 409
    code = "feature_flag_already_exists"


class AnnouncementNotFoundError(APIError):
    status_code = 404
    code = "announcement_not_found"


class AdminInvoiceNotFoundError(APIError):
    status_code = 404
    code = "invoice_not_found"


class CannotModifyOwnStaffRoleError(APIError):
    """An OWNER changing their own is_staff/staff_role could lock every
    admin out of the platform in one call (no self-service path back to
    OWNER exists) -- blocked outright, another OWNER must make the
    change."""

    status_code = 409
    code = "cannot_modify_own_staff_role"


class DailyIntelligenceSnapshotNotFoundError(APIError):
    """No `DailyIntelligenceSnapshot` row exists yet for the requested
    (or default: most recent) date -- e.g. `DailyIntelligenceAggregationScheduler`
    has never run, or the specific date requested was never aggregated."""

    status_code = 404
    code = "daily_intelligence_snapshot_not_found"


class ValidationSessionNotFoundError(APIError):
    status_code = 404
    code = "validation_session_not_found"


class ValidationSessionConflictError(APIError):
    """A RUNNING session of the same is_dry_run kind already exists, or
    the session being closed is not currently RUNNING -- see
    `src.ai_evolution.validation_session_service`."""

    status_code = 409
    code = "validation_session_conflict"
