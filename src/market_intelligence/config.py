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


def get_market_scan_symbols_per_cycle() -> int:
    """The scheduled scan's incremental batch size -- production
    evidence (2026-08-13 SAHMK quota-exhaustion incident) showed the
    scheduler re-selecting the ENTIRE active universe (372 symbols)
    every single cycle, each symbol issuing a live SAHMK quote call
    with only a 15s cache TTL (QUOTE_CACHE_TTL_SECONDS), so back-to-
    back cycles got essentially no cache benefit and burned the whole
    daily quota within about an hour of market open.

    A scheduled cycle now selects only this many symbols (the least-
    recently-scanned first -- see SymbolSelector.select's
    `prioritize_stale` -- so the full universe still gets refreshed
    over successive cycles, just not all-at-once every cycle). Default
    (20) intentionally matches SAHMK_MAX_REQUESTS_PER_MINUTE's own
    default (20/min) -- one cycle's batch comfortably fits inside a
    single per-minute rate-limiter window even at the shortest
    supported scan interval (60s), instead of a cycle spilling into
    (and starving) the next one."""
    return int(os.getenv("MARKET_SCAN_SYMBOLS_PER_CYCLE", "20"))


def get_scan_min_background_quota_remaining() -> int:
    """Circuit breaker: the scheduler skips starting a new cycle
    entirely (zero SAHMK calls, not even one) once the SAHMK rate
    limiter's own `remaining_today_for_background` estimate drops below
    this many requests -- stopping proactively, before individual
    per-symbol acquire() calls would start failing mid-scan and waste
    the partial work already done that cycle."""
    return int(os.getenv("MARKET_SCAN_MIN_BACKGROUND_QUOTA_REMAINING", "10"))


def get_scan_leader_lease_seconds() -> float:
    """TTL of the Redis leader lease `IntervalMarketIntelligenceScheduler`
    uses so only one of Gunicorn's worker processes actually drives the
    scan loop at a time (2026-08-13 incident: with no such lease, all 4
    workers independently ran the full scheduler, quadrupling real
    SAHMK volume for identical, redundant work). Renewed every tick
    while a worker holds it; a worker that crashes without releasing it
    simply lets it expire, so leadership fails over automatically."""
    return float(os.getenv("MARKET_SCAN_LEADER_LEASE_SECONDS", "180"))


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


def get_max_ohlcv_staleness_days() -> float:
    """Maximum age (days) the most recent daily PriceBar row may be
    before a symbol's technical analysis is treated as resting on
    stale history -- distinct from get_max_data_age_hours() above,
    which only checks the scan/live-quote's own freshness, not whether
    the multi-day OHLCV window indicators (SMA, momentum, etc.) are
    computed from has actually kept up. A live quote is always fresh
    (fetched fresh every scan); the underlying daily-bar history is
    only as fresh as the last successful historical_ohlcv ingestion
    run. Default of 5 covers a normal Thu/Fri Saudi weekend plus one
    full extra day of legitimate ingestion lag (a deferred run waiting
    on the next SAHMK quota reset) without falsely flagging a symbol
    the ingestion pipeline is genuinely keeping current."""
    return float(os.getenv("MARKET_MAX_OHLCV_STALENESS_DAYS", "5"))


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


def get_min_candles_for_recommendation() -> int:
    """Minimum daily bars of history a symbol must have before a BUY/
    SELL is published -- distinct from TechnicalAnalysisEngine's own
    hard floor of 35 rows (below which it cannot compute its indicator
    set at all and the symbol is skipped as insufficient_data before
    ever reaching this gate). 35 rows is "enough to not crash"; this
    default (60, ~3 trading months) is "enough recent history that a
    trend/momentum read is reasonably trustworthy" -- e.g. a stock that
    IPO'd 40 sessions ago clears the engine's own floor but not this
    one. Configurable, not empirically calibrated against a specific
    Tadawul study."""
    return int(os.getenv("MARKET_MIN_CANDLES_FOR_RECOMMENDATION", "60"))


def get_max_spread_pct() -> float:
    """Maximum real bid/ask spread (as a percent of price) a BUY/SELL
    may have to pass the abnormal-spread gate. A wide spread on an
    otherwise clean setup means the visible price is not one a real
    order could actually fill near -- the same "not really tradeable"
    concern the liquidity gate addresses via traded value, applied to
    the other real signal SAHMK's quote endpoint provides (`bid`/`ask`,
    see docs/SAHMK_INTEGRATION.md's verified field list). NOT_EVALUATED
    (never a hard fail) whenever bid/ask is unavailable for this quote,
    same convention as the liquidity gate's average-traded-value gap."""
    return float(os.getenv("MARKET_MAX_SPREAD_PCT", "3.0"))


def get_news_conflict_sentiment_threshold() -> float:
    """How strongly negative/positive (on NewsIntelligenceService's -1..1
    scale) aggregate news sentiment must be, opposite the recommended
    direction, to fail the news-conflict gate -- e.g. a BUY recommendation
    with sentiment_score <= -0.5 (clearly bad news) is flagged. Paired
    with get_news_conflict_min_articles() so a single noisy headline
    can't trip this on its own."""
    return float(os.getenv("MARKET_NEWS_CONFLICT_SENTIMENT_THRESHOLD", "0.5"))


def get_news_conflict_min_articles() -> int:
    return int(os.getenv("MARKET_NEWS_CONFLICT_MIN_ARTICLES", "2"))


def get_fundamental_conflict_margin() -> float:
    """How far (in points, on the 0-100 scale where 50 is neutral) the
    fundamental contributor's score must sit against the recommended
    direction to fail the fundamental-conflict gate -- e.g. a BUY with
    a fundamental_score of 30 (50 - 20, past the default margin of 15)
    is flagged: the technical/momentum picture may look good, but the
    fundamentals module actively disagrees, which is exactly the kind
    of contradiction a real analyst would not silently publish over."""
    return float(os.getenv("MARKET_FUNDAMENTAL_CONFLICT_MARGIN", "15.0"))


def get_min_calibrated_success_probability() -> float:
    """Minimum calibrated (not raw) success probability, 0-1, a BUY/
    SELL must clear to pass the confidence_calibration gate -- only
    ever evaluated when a real ConfidenceCalibrationEngine active model
    exists and was actually applied (see
    src.ai_evolution.confidence_calibration.get_effective_confidence);
    NOT_EVALUATED, never a hard fail, before enough real outcome
    history exists to fit one."""
    return float(os.getenv("MARKET_MIN_CALIBRATED_SUCCESS_PROBABILITY", "0.35"))


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


def get_duplicate_suppression_window_hours() -> float:
    """A newly-computed recommendation for a symbol is suppressed
    (not written as a second RecommendationSnapshot) when the most
    recent prior live-scan snapshot for that symbol, within this many
    hours, already says materially the same thing (see
    MarketIntelligenceRepository's duplicate-suppression check for the
    exact tolerance) -- prevents Live Market Mode's frequent polling
    from writing near-identical rows every cycle. A materially
    *different* call (direction or price plan actually changed) is
    never suppressed, regardless of how recently the prior one was
    published -- suppression is about noise, not about limiting how
    often real new information can update a call."""
    return float(os.getenv("MARKET_DUPLICATE_SUPPRESSION_WINDOW_HOURS", "24"))


def get_duplicate_suppression_price_tolerance_pct() -> float:
    """How close (as a percent) target/stop/entry must be between two
    snapshots for them to count as "the same call" for duplicate
    suppression."""
    return float(os.getenv("MARKET_DUPLICATE_SUPPRESSION_PRICE_TOLERANCE_PCT", "0.5"))


# --- expiration ------------------------------------------------------------


def get_expiration_days_short_term() -> int:
    """Days from publication until a RecommendationSnapshot.expires_at
    for a SHORT_TERM call (TimeHorizon.SHORT_TERM -- "days to a few
    weeks", see src.analysis.decision.types) -- a recommendation whose
    own stated horizon has elapsed with no fresh scan superseding it is
    stale, not still actionable at its original price plan."""
    return int(os.getenv("MARKET_EXPIRATION_DAYS_SHORT_TERM", "14"))


def get_expiration_days_medium_term() -> int:
    return int(os.getenv("MARKET_EXPIRATION_DAYS_MEDIUM_TERM", "45"))


def get_expiration_days_long_term() -> int:
    """Capped at 90 -- the deepest horizon
    `src.ai_evolution.outcome_evaluation.EVALUATION_HORIZON_DAYS` ever
    tracks an outcome for, so no recommendation is left "active" past
    the point this platform stops being able to score it."""
    return int(os.getenv("MARKET_EXPIRATION_DAYS_LONG_TERM", "90"))


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
    MARKET_INTELLIGENCE_SCHEDULER_ENABLED flag -- see main.py's startup
    wiring, which starts Live Market Mode's own internal market-scan
    scheduler instead of the always-on one when this is true.
    INGESTION_SCHEDULER_ENABLED is independent of this flag: the
    ingestion scheduler (symbols/historical_ohlcv/fundamentals/
    dividends backfill) always runs on its own schedule when enabled,
    regardless of Live Market Mode or market hours -- see
    live_market_mode.py's module docstring for why."""
    return os.getenv("LIVE_MARKET_MODE_ENABLED", "false").lower() == "true"


def get_live_market_mode_poll_interval_seconds() -> float:
    """How often the Live Market Mode supervisor re-checks whether the
    Tadawul session has just opened or closed, to start/stop the
    ingestion and scan schedulers accordingly. Pure datetime
    comparison (trading_calendar.is_market_open), no network call --
    a short default (60s) keeps the "start scanning right after the
    bell" latency low at negligible cost."""
    return float(os.getenv("LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS", "60"))
