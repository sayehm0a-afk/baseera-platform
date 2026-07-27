"""Durable, queryable history of every scheduled ingestion job run.

A structured log line (src.core.monitoring.structured_logging) is
still emitted for every run -- this table exists in addition, not
instead, so "when did ingestion last succeed for symbol X" or "how
many retries did last night's OHLCV run need" can be answered with a
query instead of grepping logs, and so it survives independently of
whatever log retention policy is configured in a given deployment.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class IngestionJobStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestionRunLog(Base):
    """One row per ingestion job execution.

    A row is inserted when a run starts (status=RUNNING) and updated
    in place when it finishes -- so a run that is still in progress
    (or that crashed the process before finishing) is visible as a
    RUNNING row with no finished_at, not silently absent.
    """

    __tablename__ = "ingestion_run_logs"

    id = Column(Integer, primary_key=True)
    job_name = Column(String(64), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Numeric(10, 3), nullable=True)
    symbols_requested = Column(Integer, nullable=False, default=0, server_default="0")
    symbols_succeeded = Column(Integer, nullable=False, default=0, server_default="0")
    symbols_failed = Column(Integer, nullable=False, default=0, server_default="0")
    rows_upserted = Column(Integer, nullable=False, default=0, server_default="0")
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(Enum(IngestionJobStatus), nullable=False, default=IngestionJobStatus.RUNNING)
    error_summary = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<IngestionRunLog job_name={self.job_name!r} status={self.status}>"
