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


class BacktestRunNotFoundError(APIError):
    status_code = 404
    code = "backtest_run_not_found"


class CalibrationNotFoundError(APIError):
    status_code = 404
    code = "calibration_not_found"


class InvalidBacktestConfigError(APIError):
    """A backtest request violates a bounded-workload limit (date
    range too wide, too many symbols) or references an unknown
    strategy/calibration version -- a client-correctable 422, not a
    server failure."""

    status_code = 422
    code = "invalid_backtest_config"


class DuplicateBacktestError(APIError):
    """Another large-scope backtest is already PENDING/RUNNING -- the
    "no duplicate full-market jobs" safeguard. Distinct from
    idempotency (an exact-duplicate request returns the existing run,
    200, rather than erroring at all)."""

    status_code = 409
    code = "duplicate_backtest"


class InvalidCalibrationTransitionError(APIError):
    """A calibration lifecycle action was requested from a status that
    doesn't allow it (e.g. activating a DRAFT config)."""

    status_code = 409
    code = "invalid_calibration_transition"


class ConfidenceCalibrationNotFoundError(APIError):
    """Kept distinct from CalibrationNotFoundError -- confidence-
    probability calibration (ConfidenceCalibrationModel) and
    contributor-weight calibration (CalibrationConfig) are two
    different concepts with two different version namespaces; see
    ConfidenceCalibrationModel's module docstring."""

    status_code = 404
    code = "confidence_calibration_not_found"


class InvalidConfidenceCalibrationTransitionError(APIError):
    """A confidence-calibration lifecycle action (test/activate/
    rollback) was requested from a status that doesn't allow it."""

    status_code = 409
    code = "invalid_confidence_calibration_transition"


class InsufficientCalibrationDataError(APIError):
    """Too few labeled real outcomes exist yet to propose a confidence-
    calibration model -- a legitimate "not yet" state (see
    ConfidenceCalibrationEngine.propose's min_sample_size check), not a
    server failure."""

    status_code = 422
    code = "insufficient_calibration_data"


class MarketScanRunNotFoundError(APIError):
    status_code = 404
    code = "market_scan_run_not_found"


class DuplicateMarketScanError(APIError):
    """Another MarketScanRun is already PENDING/RUNNING -- mirrors
    DuplicateBacktestError's "no overlapping full-scope jobs"
    safeguard, applied unconditionally here (unlike backtests, every
    market scan already covers the full selected universe, so there is
    no "small scope, allow it anyway" case). Overlapping scans would
    double real SAHMK request volume and race on the same DB rows
    (found in the pre-live-scan production audit)."""

    status_code = 409
    code = "duplicate_market_scan"


class NoMarketScanDataError(APIError):
    """No successful MarketScanRun exists yet -- a legitimate "not yet"
    state (no scan has ever completed), not a server failure. Every
    read endpoint under /api/v1/market/* except POST /scan and
    GET /scan/{run_id} needs at least one completed scan to read from."""

    status_code = 404
    code = "no_market_scan_data"


class PortfolioNotFoundError(APIError):
    status_code = 404
    code = "portfolio_not_found"


class NoPortfolioAnalysisError(APIError):
    """A portfolio exists but has never been analyzed -- a legitimate
    "not yet" state, not a server failure. Every read endpoint under
    /api/v1/portfolio/{id}/* needs at least one completed
    POST /api/v1/portfolio/analyze for this portfolio to read from."""

    status_code = 404
    code = "no_portfolio_analysis"


class InvalidPortfolioConfigError(APIError):
    """A portfolio request violates a bounded-workload limit (too many
    holdings) -- a client-correctable 422, not a server failure."""

    status_code = 422
    code = "invalid_portfolio_config"


class WatchlistItemAlreadyExistsError(APIError):
    """The requesting user's watchlist already contains this symbol --
    a client-correctable 409, not a server failure."""

    status_code = 409
    code = "watchlist_item_already_exists"


class WatchlistItemNotFoundError(APIError):
    """The requesting user's watchlist has no entry for this symbol."""

    status_code = 404
    code = "watchlist_item_not_found"


class SignalSnapshotNotFoundError(APIError):
    """No DecisionV2Snapshot exists with the given id."""

    status_code = 404
    code = "signal_snapshot_not_found"


class SignalNotActionableError(APIError):
    """The referenced decision is not a real BUY call (e.g. WATCH/HOLD/
    WAIT_FOR_ENTRY) -- product decision 2026-09-18: users can only
    follow real, actionable buy recommendations, matching the same
    BUY-only bias already enforced on /radar."""

    status_code = 422
    code = "signal_not_actionable"


class SignalAlreadyFollowedError(APIError):
    """The requesting user already follows this exact decision snapshot
    -- a client-correctable 409, not a server failure."""

    status_code = 409
    code = "signal_already_followed"


class PortfolioHoldingNotFoundError(APIError):
    """No PortfolioHolding row matches this (portfolio, holding) pair
    for the requesting user's portfolio."""

    status_code = 404
    code = "portfolio_holding_not_found"


class DuplicateHoldingError(APIError):
    """This portfolio already has a holding for this symbol --
    PortfolioHolding's own `uq_portfolio_holding_identity` constraint
    (one row per portfolio/stock pair); adding more of the same stock
    is an edit (PATCH) to the existing holding, not a second row."""

    status_code = 409
    code = "duplicate_holding"


class NotificationNotFoundError(APIError):
    """No Notification row matches this id for the requesting user --
    covers both a genuinely unknown id and another user's notification
    (never revealed which, to avoid leaking existence across users)."""

    status_code = 404
    code = "notification_not_found"
