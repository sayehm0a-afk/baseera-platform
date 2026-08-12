"""Unit tests for src.market_data.ingestion.config -- env var parsing only."""

from src.market_data.ingestion import config as ingestion_config


def test_scheduler_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INGESTION_SCHEDULER_ENABLED", raising=False)
    assert ingestion_config.is_ingestion_scheduler_enabled() is False


def test_scheduler_enabled_via_env(monkeypatch):
    monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "true")
    assert ingestion_config.is_ingestion_scheduler_enabled() is True


def test_scheduler_enabled_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "TRUE")
    assert ingestion_config.is_ingestion_scheduler_enabled() is True


def test_symbol_universe_defaults_to_starter_set(monkeypatch):
    monkeypatch.delenv("INGESTION_SYMBOL_UNIVERSE", raising=False)
    universe = ingestion_config.get_ingestion_symbol_universe()
    assert universe == list(ingestion_config.DEFAULT_SYMBOL_UNIVERSE)
    assert len(universe) > 0


def test_symbol_universe_reads_env(monkeypatch):
    monkeypatch.setenv("INGESTION_SYMBOL_UNIVERSE", "2222, 1120 ,1180")
    assert ingestion_config.get_ingestion_symbol_universe() == ["2222", "1120", "1180"]


def test_symbol_universe_explicitly_empty_means_empty(monkeypatch):
    """An explicit empty string is a deliberate "track nothing," not
    defaulted back to the starter set."""
    monkeypatch.setenv("INGESTION_SYMBOL_UNIVERSE", "")
    assert ingestion_config.get_ingestion_symbol_universe() == []


def test_auto_discovery_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INGESTION_AUTO_DISCOVER_SYMBOLS", raising=False)
    assert ingestion_config.is_symbol_auto_discovery_enabled() is False


def test_auto_discovery_enabled_via_env(monkeypatch):
    monkeypatch.setenv("INGESTION_AUTO_DISCOVER_SYMBOLS", "true")
    assert ingestion_config.is_symbol_auto_discovery_enabled() is True


def test_interval_defaults(monkeypatch):
    for var in (
        "INGESTION_SYMBOLS_INTERVAL_SECONDS",
        "INGESTION_OHLCV_INTERVAL_SECONDS",
        "INGESTION_FUNDAMENTALS_INTERVAL_SECONDS",
        "INGESTION_DIVIDENDS_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    assert ingestion_config.get_symbols_sync_interval_seconds() == 24 * 3600
    # Not hourly: historical_ohlcv only ever writes daily bars, so an
    # hourly cadence was pure background-quota waste -- see
    # get_ohlcv_sync_interval_seconds's own docstring for the
    # production-evidence-backed rationale.
    assert ingestion_config.get_ohlcv_sync_interval_seconds() == 6 * 3600
    assert ingestion_config.get_fundamentals_sync_interval_seconds() == 7 * 24 * 3600
    assert ingestion_config.get_dividends_sync_interval_seconds() == 24 * 3600


def test_interval_overrides(monkeypatch):
    monkeypatch.setenv("INGESTION_OHLCV_INTERVAL_SECONDS", "600")
    assert ingestion_config.get_ohlcv_sync_interval_seconds() == 600.0


def test_backfill_days_default_and_override(monkeypatch):
    monkeypatch.delenv("INGESTION_OHLCV_BACKFILL_DAYS", raising=False)
    assert ingestion_config.get_ohlcv_backfill_days() == 90
    monkeypatch.setenv("INGESTION_OHLCV_BACKFILL_DAYS", "30")
    assert ingestion_config.get_ohlcv_backfill_days() == 30


def test_fundamentals_period_type_default_and_normalization(monkeypatch):
    monkeypatch.delenv("INGESTION_FUNDAMENTALS_PERIOD_TYPE", raising=False)
    assert ingestion_config.get_fundamentals_period_type() == "annual"
    monkeypatch.setenv("INGESTION_FUNDAMENTALS_PERIOD_TYPE", "QUARTERLY")
    assert ingestion_config.get_fundamentals_period_type() == "quarterly"


def test_job_retry_config_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("INGESTION_JOB_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("INGESTION_JOB_RETRY_BASE_DELAY_SECONDS", raising=False)
    assert ingestion_config.get_ingestion_job_max_attempts() == 3
    assert ingestion_config.get_ingestion_job_retry_base_delay_seconds() == 5.0

    monkeypatch.setenv("INGESTION_JOB_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("INGESTION_JOB_RETRY_BASE_DELAY_SECONDS", "2.5")
    assert ingestion_config.get_ingestion_job_max_attempts() == 5
    assert ingestion_config.get_ingestion_job_retry_base_delay_seconds() == 2.5
