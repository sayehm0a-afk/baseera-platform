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

    # A "skipped" symbol (SymbolScanOutcome.skipped_reason set, e.g.
    # "insufficient_data"/"stock_not_registered") is not an error and
    # never populates error_summary -- but until this column existed,
    # its exact identity was computed in-memory during the scan and
    # then discarded, leaving only symbols_skipped's aggregate count
    # durable. Root-caused in production: two symbols skipped in a real
    # 393-symbol scan (run 98) had no way to be identified after the
    # fact. Populated only when symbols_skipped > 0.
    skipped_symbols_summary = Column(Text, nullable=True)

    # Radar V2 only (null for ordinary market scans): Stage 1's free,
    # full-local-universe scan size and how many of those it ranked as
    # real candidates, before Stage 2's paid live-validation cap
    # (`get_radar_stage2_candidate_cap()`) truncated the list. Populated
    # by `run_radar_v2_cycle` once Stage 2 actually executes for this
    # run -- see that function's own docstring in
    # `src.market_intelligence.radar_v2`.
    stage1_universe_size = Column(Integer, nullable=True)
    stage1_candidate_count = Column(Integer, nullable=True)

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
