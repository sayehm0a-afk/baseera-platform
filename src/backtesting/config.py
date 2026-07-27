"""Bounded-workload configuration for the Backtesting & Calibration
Engine's REST layer -- Phase 7's "use bounded date ranges and workload
limits," made concrete and env-var-configurable, matching
src.market_data.ingestion.config's own pattern (functions read the
environment at call time, not at import time, so tests can
monkeypatch them per-test)."""

import os


def get_max_backtest_symbols() -> int:
    return int(os.getenv("BACKTEST_MAX_SYMBOLS", "50"))


def get_max_backtest_range_days() -> int:
    """Ten years by default -- generous for a genuine historical study,
    still a hard ceiling against an accidental all-time request."""
    return int(os.getenv("BACKTEST_MAX_RANGE_DAYS", "3650"))


def get_full_market_symbol_threshold() -> int:
    """A request at or above this many symbols is treated as
    "full-market scope" for the duplicate-job guard (Phase 8) -- two
    such requests are never allowed to run concurrently."""
    return int(os.getenv("BACKTEST_FULL_MARKET_SYMBOL_THRESHOLD", "20"))


def get_max_trades_page_size() -> int:
    return int(os.getenv("BACKTEST_MAX_TRADES_PAGE_SIZE", "500"))
