"""Environment-driven configuration for the ingestion scheduler.

Kept separate from src.market_data.config (SAHMK connection/provider
settings) -- scheduling applies regardless of which provider is
selected, and is a distinct operational concern from "how do I talk to
SAHMK." Every setting here has a safe, conservative default; nothing
requires configuration to run, but the scheduler itself is disabled by
default (see is_ingestion_scheduler_enabled) -- the same deliberate,
secure-by-default opt-in as SAHMK_LIVE_DATA_ENABLED: an operator must
turn scheduled ingestion on, it never starts silently.
"""

import os
from typing import List

# A small, well-known starting set of heavily-traded Tadawul symbols --
# a reasonable default so the scheduler does something useful the
# moment it's enabled, not a claim that these particular stocks matter
# more than any other. Override via INGESTION_SYMBOL_UNIVERSE.
DEFAULT_SYMBOL_UNIVERSE = ("2222", "1120", "2010", "1180", "7010")


def is_ingestion_scheduler_enabled() -> bool:
    return os.getenv("INGESTION_SCHEDULER_ENABLED", "false").strip().lower() == "true"


def get_ingestion_symbol_universe() -> List[str]:
    """Comma-separated list of Tadawul symbols to keep ingested
    (OHLCV/fundamentals/dividends), e.g. "2222,1120,2010". Falls back
    to DEFAULT_SYMBOL_UNIVERSE if unset -- explicitly empty
    (INGESTION_SYMBOL_UNIVERSE="") means "track nothing," a deliberate
    choice, not a misconfiguration defaulted away."""
    raw = os.getenv("INGESTION_SYMBOL_UNIVERSE")
    if raw is None:
        return list(DEFAULT_SYMBOL_UNIVERSE)
    return [s.strip() for s in raw.split(",") if s.strip()]


def is_symbol_auto_discovery_enabled() -> bool:
    """If true, the symbols job also registers every symbol the
    provider's own directory reports (SahmkMarketDataProvider only),
    not just INGESTION_SYMBOL_UNIVERSE. Off by default -- discovering
    the full ~350-symbol Tadawul+Nomu universe is a heavier, deliberate
    choice, not an automatic consequence of enabling the scheduler."""
    return os.getenv("INGESTION_AUTO_DISCOVER_SYMBOLS", "false").strip().lower() == "true"


def get_symbols_sync_interval_seconds() -> float:
    return float(os.getenv("INGESTION_SYMBOLS_INTERVAL_SECONDS", str(24 * 3600)))


def get_ohlcv_sync_interval_seconds() -> float:
    """Default is 6 hours, not hourly. historical_ohlcv only ever writes
    Timeframe.ONE_DAY bars (see ingest_historical_ohlcv.py) -- a daily
    bar changes at most once per trading day, so an hourly cadence was
    pure waste: at ~385 active symbols and one SAHMK call per symbol
    per run (no caching layer sits in front of this -- each run
    genuinely asks "anything new since last time" per symbol), hourly
    meant up to 385*24 = 9,240 background-quota calls attempted per
    day against a 3,500/day background budget -- confirmed by real
    2026-08-11 production evidence: requests_used_today had already
    hit the 3,500 background cap by 22:03 UTC, and every scheduled job
    that hour (symbols/historical_ohlcv/fundamentals/dividends) was
    correctly refused by the quota governor. Every 6 hours (4 runs/day
    = ~1,540 calls/day) comfortably covers a post-close refresh plus
    catch-up slack for newly-discovered symbols, while leaving real
    headroom in the background budget for dividends (~385/day) and
    fundamentals (~385/week). Still fully overridable via
    INGESTION_OHLCV_INTERVAL_SECONDS."""
    return float(os.getenv("INGESTION_OHLCV_INTERVAL_SECONDS", str(6 * 3600)))


def get_ohlcv_sync_next_delay_seconds() -> float:
    """What `IngestionScheduler`'s job loop actually uses to schedule
    `historical_ohlcv`'s *next* run (see ingestion/scheduler.py's
    job_specs) -- calendar-aware and once-per-trading-day by default,
    replacing the fixed-interval cadence `get_ohlcv_sync_interval_
    seconds` still represents.

    If `INGESTION_OHLCV_INTERVAL_SECONDS` is explicitly set, honors it
    verbatim (the pre-existing fixed-interval override, preserved as an
    operator escape hatch for whoever needs a different cadence than
    "once daily, shortly after Tadawul close"). Otherwise delegates to
    `trading_calendar.seconds_until_next_ohlcv_sync()`, which computes
    the real number of seconds until the next post-close sync window --
    the once-per-trading-day-at-the-correct-time default a daily bar
    actually needs (see that function's own docstring for the real
    production-quota-exhaustion history behind this change).
    """
    raw = os.getenv("INGESTION_OHLCV_INTERVAL_SECONDS")
    if raw is not None:
        return float(raw)
    from src.market_intelligence.trading_calendar import seconds_until_next_ohlcv_sync

    return seconds_until_next_ohlcv_sync()


def get_fundamentals_sync_interval_seconds() -> float:
    return float(os.getenv("INGESTION_FUNDAMENTALS_INTERVAL_SECONDS", str(7 * 24 * 3600)))


def get_dividends_sync_interval_seconds() -> float:
    return float(os.getenv("INGESTION_DIVIDENDS_INTERVAL_SECONDS", str(24 * 3600)))


def get_sector_recheck_days() -> int:
    """How long a symbol whose per-symbol company-profile fetch found no
    sector data is left alone before sync_symbols() tries it again --
    bounds retries of a genuinely provider-side gap without retrying it
    on every single sync run forever."""
    return int(os.getenv("INGESTION_SECTOR_RECHECK_DAYS", "30"))


def get_ohlcv_backfill_days() -> int:
    """How many days of history to backfill the first time a symbol is
    ingested (subsequent runs are incremental regardless of this
    value -- see ingest_historical_ohlcv.py). Used for the BACKGROUND-
    priority pass (Tiers 2-4) -- see get_critical_refresh_backfill_days()
    for the smaller value the CRITICAL-priority pass (Tiers 0-1) uses."""
    return int(os.getenv("INGESTION_OHLCV_BACKFILL_DAYS", "90"))


def get_critical_refresh_backfill_days() -> int:
    """P0 SAHMK quota architecture repair (2026-08-25), Section 7's
    DAILY_CRITICAL_REFRESH: how many days of history to backfill for a
    Tier 0/1 (active-position/pending-signal) symbol that somehow has
    zero PriceBar rows yet -- deliberately much smaller than
    get_ohlcv_backfill_days()'s default (90): a symbol only reaches
    Tier 0/1 by already having a DecisionV2Snapshot/DecisionV2Outcome,
    which itself requires prior price history to have been computed,
    so this case is expected to be rare. For the overwhelmingly common
    case (a Tier 0/1 symbol that already has bars),
    ingest_historical_ohlcv.py's own incremental catch-up already
    requests only from the latest ingested day forward regardless of
    this value -- it only bounds the rare zero-history edge case, which
    is exactly what keeps the critical pass small and bounded as
    Section 7 requires."""
    return int(os.getenv("INGESTION_CRITICAL_REFRESH_BACKFILL_DAYS", "5"))


def get_fundamentals_period_type() -> str:
    return os.getenv("INGESTION_FUNDAMENTALS_PERIOD_TYPE", "annual").strip().lower()


def get_ingestion_job_max_attempts() -> int:
    """Job-level retry: if an entire job run raises (a DB connection
    blip, an unexpected exception escaping per-symbol isolation) --
    distinct from SahmkClient's own per-request retry, this is about
    the job as a whole failing to complete at all."""
    return int(os.getenv("INGESTION_JOB_MAX_ATTEMPTS", "3"))


def get_ingestion_job_retry_base_delay_seconds() -> float:
    return float(os.getenv("INGESTION_JOB_RETRY_BASE_DELAY_SECONDS", "5"))


def get_ingestion_leader_lease_seconds() -> float:
    """TTL of the Redis leader lease `IngestionScheduler` uses so only
    one of Gunicorn's worker processes actually performs scheduled
    ingestion work at a time -- mirrors `MarketIntelligenceScheduler`'s
    own `MARKET_SCAN_LEADER_LEASE_SECONDS` lease/renewal pattern
    (`scheduler_leader_lock.SchedulerLeaderLock`), applied to a second,
    independent lease key so the two schedulers' leaderships are
    tracked separately. Renewed on its own short heartbeat
    (`get_ingestion_leader_heartbeat_seconds`), deliberately independent
    of any single ingestion job's own (often much longer, e.g. daily or
    weekly) recurring interval -- a worker that crashes without
    releasing the lease simply lets it expire, so leadership fails over
    to another worker automatically."""
    return float(os.getenv("INGESTION_SCHEDULER_LEADER_LEASE_SECONDS", "180"))


def get_ingestion_leader_heartbeat_seconds() -> float:
    """How often `IngestionScheduler`'s dedicated leadership heartbeat
    task re-attempts/renews its Redis lease. Deliberately independent
    of any ingestion job's own interval (which can be as long as 7
    days) -- leadership itself transfers to a new worker within roughly
    this many seconds after the previous leader's process dies, even
    though the new leader's first actual job run still waits for that
    job's own normal schedule (never runs a job early just because
    leadership just changed hands)."""
    return float(os.getenv("INGESTION_SCHEDULER_LEADER_HEARTBEAT_SECONDS", "30"))


def get_max_ingestion_job_run_duration_hours() -> float:
    """Mirrors src.market_intelligence.config.get_max_scan_run_duration_hours's
    reap_stale_runs pattern for the same underlying failure mode: a
    process killed/restarted between run_ingestion_job's RUNNING insert
    and its finished_at update leaves an IngestionRunLog row RUNNING
    forever, which would otherwise permanently block every future
    POST /full-discovery (its in-flight guard matches on
    finished_at IS NULL with no staleness check). A full discovery
    pass can legitimately run for "many minutes" per that route's own
    docstring, so this default is generous, not tight."""
    return float(os.getenv("INGESTION_MAX_JOB_RUN_DURATION_HOURS", "6"))
