"""API-layer exceptions -- each maps to exactly one HTTP status code
and a stable, machine-readable `code` via src.api.error_handlers, so a
frontend can branch on `error.code` instead of parsing `message` text.
"""


class APIError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class StockNotFoundError(APIError):
    status_code = 404
    code = "stock_not_found"


class InsufficientDataError(APIError):
    """Not enough historical bars/fundamental periods to run an
    analysis engine -- a legitimate "not yet" state, not a server
    failure (e.g. a newly-added symbol with only a few ingested days)."""

    status_code = 422
    code = "insufficient_data"


class ProviderUnavailableError(APIError):
    """The selected market/fundamental data provider could not satisfy
    this request (SAHMK unreachable/rejected and no cached data exists
    to fall back to)."""

    status_code = 503
    code = "provider_unavailable"


class InvalidSymbolFormatError(APIError):
    status_code = 422
    code = "invalid_symbol_format"
