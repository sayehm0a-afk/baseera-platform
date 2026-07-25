"""MarketScanRun: the durable record of one Autonomous Market
Intelligence Layer scan execution -- its status/progress (so a
full-market scan can be polled instead of blocking an HTTP request,
the same shape BacktestRun already established) and its final
symbol-level counters. This is the layer's "scan history."
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Integer, Numeric, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class MarketScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class MarketScanRun(Base):
    __tablename__ = "market_scan_runs"

    id = Column(Integer, primary_key=True)
    status = Column(Enum(MarketScanStatus), nullable=False, default=MarketScanStatus.PENDING)

    symbols_requested = Column(Integer, nullable=False, default=0, server_default="0")
    symbols_succeeded = Column(Integer, nullable=False, default=0, server_default="0")
    symbols_skipped = Column(Integer, nullable=False, default=0, server_default="0")
    symbols_failed = Column(Integer, nullable=False, default=0, server_default="0")

    error_summary = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Numeric(10, 3), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<MarketScanRun id={self.id} status={self.status}>"
