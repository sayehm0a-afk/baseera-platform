"""SectorIntelligenceSummary: one sector's aggregate stats for one
MarketScanRun -- persisted (unlike rankings/watchlists, see
symbol_intelligence_record.py's docstring) because sector momentum
needs a t-1 comparison, and re-deriving every historical scan's sector
aggregates on every read to support that would be wasteful for
something checked repeatedly; this is a small, one-row-per-sector-
per-scan table, not a per-symbol duplication.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class SectorIntelligenceSummary(Base):
    __tablename__ = "sector_intelligence_summaries"
    __table_args__ = (
        UniqueConstraint("scan_run_id", "sector", name="uq_sector_intelligence_summary_identity"),
    )

    id = Column(Integer, primary_key=True)
    scan_run_id = Column(Integer, ForeignKey("market_scan_runs.id"), nullable=False, index=True)
    sector = Column(String(128), nullable=False, index=True)

    symbol_count = Column(Integer, nullable=False)
    average_confidence = Column(Numeric(6, 2), nullable=True)
    average_final_score = Column(Numeric(6, 2), nullable=True)
    average_expected_return_pct = Column(Numeric(9, 4), nullable=True)
    average_technical_score = Column(Numeric(6, 2), nullable=True)
    average_fundamental_score = Column(Numeric(6, 2), nullable=True)
    buy_count = Column(Integer, nullable=False, default=0, server_default="0")
    sell_count = Column(Integer, nullable=False, default=0, server_default="0")
    hold_count = Column(Integer, nullable=False, default=0, server_default="0")
    breadth = Column(Numeric(6, 4), nullable=False)
    momentum = Column(Numeric(9, 4), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    scan_run = relationship("MarketScanRun")

    def __repr__(self) -> str:
        return f"<SectorIntelligenceSummary sector={self.sector!r} scan_run_id={self.scan_run_id}>"
