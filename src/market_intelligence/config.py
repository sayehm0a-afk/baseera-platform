"""Env-var configurable settings for the Autonomous Market Intelligence
Layer -- matches src.market_data.ingestion.config's and
src.backtesting.config's own pattern (functions read the environment
at call time, not at import time, so tests can monkeypatch them
per-test).
"""

import os

from src.market_intelligence.types import ScheduleInterval

_SCHEDULE_INTERVAL_SECONDS = {
    ScheduleInterval.EVERY_MINUTE: 60,
    ScheduleInterval.EVERY_5_MINUTES: 300,
    ScheduleInterval.HOURLY: 3600,
    ScheduleInterval.DAILY: 86400,
    ScheduleInterval.WEEKLY: 604800,
}


def schedule_interval_seconds(interval: ScheduleInterval) -> int:
    return _SCHEDULE_INTERVAL_SECONDS[interval]


# --- scanner -----------------------------------------------------------


def get_scan_batch_size() -> int:
    """How many symbols' scans may be in flight at once (see
    MarketScanner's asyncio.Semaphore). 1 by default -- a scan is
    already useful sequentially, and each symbol's own DB session must
    not be shared across concurrent tasks; raising this is safe once a
    deployment's DB pool is sized for it."""
    return int(os.getenv("MARKET_SCAN_BATCH_SIZE", "1"))


def get_scan_max_attempts() -> int:
    return int(os.getenv("MARKET_SCAN_MAX_ATTEMPTS", "2"))


def get_scan_retry_base_delay_seconds() -> float:
    return float(os.getenv("MARKET_SCAN_RETRY_BASE_DELAY_SECONDS", "1.0"))


def get_scan_max_symbols() -> int:
    """A bounded-workload ceiling, same reasoning as
    BACKTEST_MAX_SYMBOLS -- generous for the full TASI+Nomu universe,
    still a hard limit against an accidental unbounded request."""
    return int(os.getenv("MARKET_SCAN_MAX_SYMBOLS", "500"))


def is_price_history_required_for_scan() -> bool:
    """SymbolSelector skips a symbol with zero ingested PriceBar rows
    when true (the default) -- such a symbol cannot produce a
    technical leg, and most likely has no fundamentals either, so
    scanning it would only ever produce a skipped/insufficient-data
    outcome."""
    return os.getenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "true").lower() == "true"


# --- rankings / watchlists ----------------------------------------------


def get_ranking_top_n() -> int:
    return int(os.getenv("MARKET_RANKING_TOP_N", "20"))


def get_watchlist_max_size() -> int:
    return int(os.getenv("MARKET_WATCHLIST_MAX_SIZE", "30"))


def get_momentum_adx_threshold() -> float:
    return float(os.getenv("MARKET_MOMENTUM_ADX_THRESHOLD", "25.0"))


def get_oversold_rsi_threshold() -> float:
    return float(os.getenv("MARKET_OVERSOLD_RSI_THRESHOLD", "30.0"))


def get_overbought_rsi_threshold() -> float:
    return float(os.getenv("MARKET_OVERBOUGHT_RSI_THRESHOLD", "70.0"))


def get_dividend_yield_threshold() -> float:
    """Fractional, not percent -- 0.03 == 3% -- matching
    FundamentalAnalysisResult.dividend_yield's own units."""
    return float(os.getenv("MARKET_DIVIDEND_YIELD_THRESHOLD", "0.03"))


# --- change detection ------------------------------------------------------


def get_score_change_threshold() -> float:
    """Minimum |delta| in final_score (0-100 scale) between two scans
    to be recorded as a SCORE_CHANGE event -- below this, day-to-day
    noise in the underlying indicators/ratios is not worth surfacing."""
    return float(os.getenv("MARKET_SCORE_CHANGE_THRESHOLD", "3.0"))


def get_confidence_change_threshold() -> float:
    return float(os.getenv("MARKET_CONFIDENCE_CHANGE_THRESHOLD", "5.0"))


def get_target_price_change_threshold_pct() -> float:
    return float(os.getenv("MARKET_TARGET_PRICE_CHANGE_THRESHOLD_PCT", "5.0"))


# --- alerts --------------------------------------------------------------


def get_alert_confidence_threshold() -> float:
    return float(os.getenv("MARKET_ALERT_CONFIDENCE_THRESHOLD", "85.0"))


def get_sector_rotation_momentum_threshold() -> float:
    """Minimum |momentum| (average_final_score delta vs the previous
    scan) for a sector to be flagged as rotating, both for the
    SECTOR_ROTATION alert and for SectorAnalyzer.rotation()."""
    return float(os.getenv("MARKET_SECTOR_ROTATION_MOMENTUM_THRESHOLD", "5.0"))


def get_alert_risk_spike_confidence_drop() -> float:
    """A RISK_SPIKE alert fires when risk_level worsens AND confidence
    drops by at least this many points in the same scan -- a
    risk-level change alone can be routine (e.g. ATR-driven); pairing
    it with a confidence drop is what distinguishes a genuine warning
    from ordinary volatility."""
    return float(os.getenv("MARKET_ALERT_RISK_SPIKE_CONFIDENCE_DROP", "10.0"))


# --- market snapshot --------------------------------------------------------


def get_snapshot_top_changes_count() -> int:
    return int(os.getenv("MARKET_SNAPSHOT_TOP_CHANGES_COUNT", "10"))


def get_snapshot_top_sectors_count() -> int:
    return int(os.getenv("MARKET_SNAPSHOT_TOP_SECTORS_COUNT", "5"))


# --- scheduler -------------------------------------------------------------


def is_market_intelligence_scheduler_enabled() -> bool:
    return os.getenv("MARKET_INTELLIGENCE_SCHEDULER_ENABLED", "false").lower() == "true"


def get_market_intelligence_scan_interval() -> ScheduleInterval:
    raw = os.getenv("MARKET_INTELLIGENCE_SCAN_INTERVAL", ScheduleInterval.DAILY.value)
    return ScheduleInterval(raw)
