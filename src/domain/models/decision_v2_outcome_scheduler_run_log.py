"""AUDIT 2026-09-11 (item #6): durable, queryable history of every
`DecisionV2OutcomeScheduler` cycle -- mirrors `IngestionRunLog`'s own
rationale exactly (a structured log line is still emitted too; this
table exists in addition, not instead, so "did the last cycle actually
run, and what did it produce" can be answered with a query instead of
grepping logs, surviving independently of log retention).

Before this table existed, `DecisionV2OutcomeScheduler._run_one_cycle`
only ever logged via `logger.info` -- there was no way for an admin
surface to distinguish "the scheduler is genuinely idle because there
is nothing pending" from "the scheduler crashed three days ago and
nobody noticed." A row is inserted when a cycle starts (status=RUNNING)
and updated in place when it finishes, same convention as
IngestionRunLog, so a crashed-mid-cycle row is visible as a stale
RUNNING row rather than silently absent.

Only ever written by the worker currently holding the scheduler's
leader lease -- a follower tick that skips its own work (see the
scheduler's own class docstring) writes zero rows here, by design,
so multiple Gunicorn workers never produce duplicate rows for what is
logically one cycle.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Integer, Numeric, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class DecisionV2OutcomeSchedulerRunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class DecisionV2OutcomeSchedulerRunLog(Base):
    """One row per `DecisionV2OutcomeScheduler` cycle."""

    __tablename__ = "decision_v2_outcome_scheduler_run_logs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Numeric(10, 3), nullable=True)
    evaluated_terminal = Column(Integer, nullable=False, default=0, server_default="0")
    data_unavailable = Column(Integer, nullable=False, default=0, server_default="0")
    cancelled = Column(Integer, nullable=False, default=0, server_default="0")
    still_pending = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(
        Enum(DecisionV2OutcomeSchedulerRunStatus),
        nullable=False,
        default=DecisionV2OutcomeSchedulerRunStatus.RUNNING,
    )
    error_summary = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<DecisionV2OutcomeSchedulerRunLog status={self.status}>"
