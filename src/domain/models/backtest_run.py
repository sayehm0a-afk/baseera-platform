"""BacktestRun: the durable record of one BacktestingEngine execution
-- its configuration (frozen at submission time, for reproducibility),
its progress/status (so a long-running full-market backtest can be
polled instead of blocking an HTTP request, per the REST layer's
requirements), and its final metrics.

`idempotency_key` is a deterministic hash of the run's configuration
(symbols, date range, frequency, strategy, cost assumptions, ...) --
submitting the same configuration twice returns the existing run
instead of launching a duplicate, and is also what a "reject a second
concurrent full-market job" guard checks against.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class BacktestRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DataProvenanceMode(str, enum.Enum):
    """What kind of PriceBar data a run is permitted/observed to use --
    the enforcement mechanism behind "never mix synthetic and live
    performance into one reported result." A run's evaluations are
    checked against this as they execute; a symbol/date whose bars
    don't match the declared mode is skipped and recorded, never
    silently blended in."""

    SYNTHETIC = "SYNTHETIC"
    LIVE = "LIVE"


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(Enum(BacktestRunStatus), nullable=False, default=BacktestRunStatus.PENDING)

    # --- configuration, frozen at submission time ---
    symbols = Column(JSON, nullable=False)  # List[str]; a full-universe run stores the resolved list
    strategy = Column(String(64), nullable=False, default="ai_decision_engine", server_default="ai_decision_engine")
    data_provenance_mode = Column(Enum(DataProvenanceMode), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    evaluation_frequency_days = Column(Integer, nullable=False, default=7, server_default="7")
    holding_horizon_days = Column(Integer, nullable=False, default=20, server_default="20")
    target_price_horizon_days = Column(Integer, nullable=False, default=60, server_default="60")
    transaction_cost_bps = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    slippage_bps = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    confidence_threshold = Column(Numeric(6, 2), nullable=True)
    recommendation_threshold = Column(String(16), nullable=True)
    fundamental_reporting_lag_days = Column(Integer, nullable=False, default=45, server_default="45")
    calibration_version = Column(String(64), nullable=True)
    random_seed = Column(Integer, nullable=True)

    # --- progress / lifecycle ---
    progress_current = Column(Integer, nullable=False, default=0, server_default="0")
    progress_total = Column(Integer, nullable=False, default=0, server_default="0")
    cancel_requested = Column(Boolean, nullable=False, default=False, server_default="false")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Numeric(10, 3), nullable=True)

    # --- results ---
    metrics = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    snapshots = relationship("RecommendationSnapshot", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<BacktestRun id={self.id} status={self.status} symbols={len(self.symbols or [])}>"
