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
    return float(os.getenv("INGESTION_OHLCV_INTERVAL_SECONDS", str(3600)))


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
    value -- see ingest_historical_ohlcv.py)."""
    return int(os.getenv("INGESTION_OHLCV_BACKFILL_DAYS", "90"))


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
