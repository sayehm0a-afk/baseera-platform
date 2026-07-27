"""Env-configurable constants for the News Intelligence Engine --
functions read the environment at call time (not import time), the
same `src.market_data.ingestion.config`/`src.backtesting.config`
pattern already used throughout this codebase, so tests can
monkeypatch the underlying env vars per-test.
"""

import os


def get_news_fetch_limit() -> int:
    """How many recent items to request from the provider per collection
    pass."""
    return int(os.getenv("NEWS_FETCH_LIMIT", "20"))


def get_news_fetch_cache_ttl_seconds() -> float:
    """How long a raw-provider-fetch result is reused before re-hitting
    the (metered, Pro+-gated) upstream endpoint -- matches
    SahmkMarketDataService's own EVENTS_CACHE_TTL_SECONDS default."""
    return float(os.getenv("NEWS_FETCH_CACHE_TTL_SECONDS", "300"))


def get_news_sentiment_lookback_days() -> int:
    """How far back an event still counts toward a symbol's current
    aggregate sentiment."""
    return int(os.getenv("NEWS_SENTIMENT_LOOKBACK_DAYS", "7"))


def get_news_dedup_similarity_threshold() -> float:
    """Normalized-headline similarity (difflib ratio, 0-1) at or above
    which two articles are treated as the same underlying story."""
    return float(os.getenv("NEWS_DEDUP_SIMILARITY_THRESHOLD", "0.85"))


def get_news_dedup_lookback_hours() -> int:
    """How far back to look for a possible canonical event when
    deciding whether a newly collected article is a duplicate."""
    return int(os.getenv("NEWS_DEDUP_LOOKBACK_HOURS", "72"))


def get_default_source_reliability() -> float:
    """The conservative reliability score a source neither seen before
    nor manually configured gets on first sight."""
    return float(os.getenv("NEWS_DEFAULT_SOURCE_RELIABILITY", "0.5"))


def get_llm_model_name() -> str:
    return os.getenv("NEWS_LLM_MODEL", "gpt-4o-mini")


def get_max_events_per_symbol_sentiment() -> int:
    """How many of a symbol's most-impactful recent events are surfaced
    individually (as separate Signals) in the decision engine's
    explainability breakdown -- matches
    AIDecisionEngine's own _MAX_REASON_SIGNALS-style capping so news
    alone can't flood the reasons list."""
    return int(os.getenv("NEWS_MAX_EVENTS_PER_SYMBOL_SENTIMENT", "5"))


def get_alert_major_opportunity_threshold() -> float:
    """Minimum sentiment_score (0..1 magnitude) plus minimum confidence
    (0..100) an event needs to trigger a MAJOR_OPPORTUNITY portfolio
    alert -- see news_intelligence.portfolio_alerts."""
    return float(os.getenv("NEWS_ALERT_MAJOR_OPPORTUNITY_SENTIMENT_THRESHOLD", "0.6"))


def get_alert_high_risk_sentiment_threshold() -> float:
    return float(os.getenv("NEWS_ALERT_HIGH_RISK_SENTIMENT_THRESHOLD", "-0.5"))


def get_alert_min_confidence() -> float:
    """No portfolio alert fires below this confidence, regardless of
    how extreme the sentiment score looks -- a low-confidence read
    (thin/duplicate/unreliable-source evidence) should never trigger an
    action-worthy alert."""
    return float(os.getenv("NEWS_ALERT_MIN_CONFIDENCE", "55.0"))
