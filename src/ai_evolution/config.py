"""Config for the AI Evolution Layer's background jobs -- same
env-var-driven, secure/inert-by-default pattern every other scheduler
in this codebase already uses (`INGESTION_SCHEDULER_ENABLED`,
`MARKET_INTELLIGENCE_SCHEDULER_ENABLED`).
"""

import os

_DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60  # daily
_DEFAULT_STALE_GRACE_DAYS = 14
_DEFAULT_WEEKLY_INTERVAL_SECONDS = 7 * 24 * 60 * 60


def is_outcome_evaluation_scheduler_enabled() -> bool:
    return os.getenv("OUTCOME_EVALUATION_SCHEDULER_ENABLED", "false").lower() == "true"


def get_outcome_evaluation_interval_seconds() -> int:
    return int(os.getenv("OUTCOME_EVALUATION_INTERVAL_SECONDS", str(_DEFAULT_INTERVAL_SECONDS)))


def get_outcome_evaluation_stale_grace_days() -> int:
    """How many days past `due_at` a PENDING outcome may wait for
    forward price data before it's given up on (marked EXPIRED with no
    price data) instead of retried forever -- covers a delisted symbol
    or a permanent data-ingestion gap, not the normal case."""
    return int(os.getenv("OUTCOME_EVALUATION_STALE_GRACE_DAYS", str(_DEFAULT_STALE_GRACE_DAYS)))


def is_pattern_discovery_scheduler_enabled() -> bool:
    return os.getenv("PATTERN_DISCOVERY_SCHEDULER_ENABLED", "false").lower() == "true"


def get_pattern_discovery_interval_seconds() -> int:
    return int(os.getenv("PATTERN_DISCOVERY_INTERVAL_SECONDS", str(_DEFAULT_WEEKLY_INTERVAL_SECONDS)))


def is_daily_reflection_scheduler_enabled() -> bool:
    return os.getenv("DAILY_REFLECTION_SCHEDULER_ENABLED", "false").lower() == "true"


def get_daily_reflection_interval_seconds() -> int:
    return int(os.getenv("DAILY_REFLECTION_INTERVAL_SECONDS", str(_DEFAULT_INTERVAL_SECONDS)))


def is_agent_panel_enabled() -> bool:
    """Gates the entire E7 agent panel, independent of whether real
    LLM calls are also enabled (see `is_agent_panel_llm_enabled`) --
    even the non-LLM wrapper agents write a real `agent_opinions` row
    per scanned symbol, real DB write volume an operator should opt
    into explicitly, the same disabled-by-default posture every
    scheduler in this codebase already uses."""
    return os.getenv("AGENT_PANEL_ENABLED", "false").lower() == "true"


def is_agent_panel_llm_enabled() -> bool:
    """True iff a real OPENAI_API_KEY is configured -- same convention
    `src.analysis.analyst.config.is_analyst_llm_narration_enabled` and
    `src.news_intelligence.config` already use. False is the honest
    default: News/Sentiment/Judge report UNAVAILABLE rather than
    fabricating an opinion."""
    return bool(os.getenv("OPENAI_API_KEY"))


def is_daily_intelligence_aggregation_scheduler_enabled() -> bool:
    return os.getenv("DAILY_INTELLIGENCE_AGGREGATION_SCHEDULER_ENABLED", "false").lower() == "true"


def get_daily_intelligence_aggregation_interval_seconds() -> int:
    return int(os.getenv("DAILY_INTELLIGENCE_AGGREGATION_INTERVAL_SECONDS", str(_DEFAULT_INTERVAL_SECONDS)))


def is_paper_trading_enabled() -> bool:
    """Gates E8's champion/challenger paper trading -- when off (the
    default), `save_symbol_records` writes only the ordinary champion
    snapshot, unchanged from before E8 existed. When on, every scanned
    symbol also gets a second, `is_paper_trade=True` challenger
    snapshot scored against the latest VALIDATED (not yet ACTIVE)
    `CalibrationConfig`, if one exists -- real extra DB write volume an
    operator should opt into explicitly, same posture as every other
    scheduler/feature in this layer."""
    return os.getenv("PAPER_TRADING_ENABLED", "false").lower() == "true"
