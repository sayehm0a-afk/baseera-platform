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
