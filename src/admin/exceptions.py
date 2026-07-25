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
