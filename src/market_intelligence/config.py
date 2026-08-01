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


def get_scan_symbol_timeout_seconds() -> float:
    """Hard wall-clock ceiling on one symbol's entire _scan_one() (DB
    query + every SAHMK call + LLM narration), independent of each
    individual leg's own timeout -- without this, a single
    pathologically slow symbol has no ceiling on how large a share of
    a long full-market scan's time budget it can consume (found in the
    pre-live-scan production audit). Default (240s) comfortably covers
    the worst realistic case: several sequential SAHMK requests each
    up to ~33.5s (10s request timeout x up to 3 tenacity attempts with
    backoff) plus the analyst LLM call's own 12s ceiling
    (ANALYST_LLM_TIMEOUT_SECONDS)."""
    return float(os.getenv("MARKET_SCAN_SYMBOL_TIMEOUT_SECONDS", "240"))


def is_price_history_required_for_scan() -> bool:
    """SymbolSelector skips a symbol with zero ingested PriceBar rows
    when true (the default) -- such a symbol cannot produce a
    technical leg, and most likely has no fundamentals either, so
    scanning it would only ever produce a skipped/insufficient-data
    outcome."""
    return os.getenv("MARKET_SCAN_REQUIRE_PRICE_HISTORY", "true").lower() == "true"


def get_max_scan_run_duration_hours() -> float:
    """A PENDING/RUNNING MarketScanRun older than this is treated as
    crashed/cancelled (its process died without ever calling
    finish_run) and reaped -- see MarketIntelligenceRepository.
    reap_stale_runs(). Default (4h) is set above
    sahmk-live-pipeline-validation.yml's own 3h full_universe timeout,
    so a legitimately still-running full-market scan is never reaped
    out from under itself."""
    return float(os.getenv("MARKET_MAX_SCAN_RUN_DURATION_HOURS", "4"))


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


# --- publication gate -------------------------------------------------------


def get_max_data_age_hours() -> float:
    """Maximum age (hours, from SymbolScanOutcome.scanned_at to now) a
    scan outcome may be and still be published. Basirah is a daily-bar
    system with no live intraday feed (see docs/basirah_intelligence_core/
    PHASE_0_REALITY_AUDIT.md), so 24h is a reasonable default for
    "still represents today's/yesterday's close," not a claim of
    real-time freshness."""
    return float(os.getenv("MARKET_MAX_DATA_AGE_HOURS", "24"))


def get_min_average_traded_value() -> float:
    """Minimum average daily traded value (price x 20-period average
    volume, in SAR) for a BUY/SELL to pass the liquidity gate. This is
    a conservative placeholder, not a value empirically calibrated
    against real Tadawul liquidity distributions -- disclosed as a
    known limitation (see docs/basirah_intelligence_core/
    PHASE_0_REALITY_AUDIT.md, defect #1) pending that calibration work.
    Configurable so it can be tightened/loosened without a code change
    once real liquidity-tier data is available."""
    return float(os.getenv("MARKET_MIN_AVERAGE_TRADED_VALUE_SAR", "1000000"))


def get_min_risk_reward_ratio() -> float:
    """Below this reward:risk ratio, a BUY/SELL is rejected outright by
    publication_gate.py rather than merely shrunk in position size.
    Reuses AIDecisionTuning.poor_risk_reward_threshold's existing value
    (1.0) as the default -- the same threshold `_derive_position_size`
    already treats as "poor" -- rather than inventing a second,
    uncoordinated number; a ratio below 1.0 means the position risks
    more than it can gain, which no position-size adjustment alone can
    make an acceptable trade."""
    return float(os.getenv("MARKET_MIN_RISK_REWARD_RATIO", "1.0"))


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


# --- Live Market Mode --------------------------------------------------------


def is_live_market_mode_enabled() -> bool:
    """Gates LiveMarketModeScheduler (see live_market_mode.py). Meant
    as an alternative to, not additive with, the standalone
    MARKET_INTELLIGENCE_SCHEDULER_ENABLED/INGESTION_SCHEDULER_ENABLED
    flags -- see main.py's startup wiring, which starts Live Market
    Mode's own internal instances of those two schedulers instead of
    the always-on ones when this is true."""
    return os.getenv("LIVE_MARKET_MODE_ENABLED", "false").lower() == "true"


def get_live_market_mode_poll_interval_seconds() -> float:
    """How often the Live Market Mode supervisor re-checks whether the
    Tadawul session has just opened or closed, to start/stop the
    ingestion and scan schedulers accordingly. Pure datetime
    comparison (trading_calendar.is_market_open), no network call --
    a short default (60s) keeps the "start scanning right after the
    bell" latency low at negligible cost."""
    return float(os.getenv("LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS", "60"))
