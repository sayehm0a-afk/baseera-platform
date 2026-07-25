"""MarketChangeEvent: one diff produced by
src.market_intelligence.change_detector comparing one scan against the
previous one -- durable change history, and the source data for the
MOST_IMPROVED_TODAY/MOST_DETERIORATED_TODAY/NEW_OPPORTUNITIES/
REMOVED_OPPORTUNITIES/RECENTLY_UPGRADED/RECENTLY_DOWNGRADED rankings.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class ChangeType(str, enum.Enum):
    RECOMMENDATION_CHANGE = "RECOMMENDATION_CHANGE"
    CONFIDENCE_CHANGE = "CONFIDENCE_CHANGE"
    SCORE_CHANGE = "SCORE_CHANGE"
    TARGET_PRICE_CHANGE = "TARGET_PRICE_CHANGE"
    RISK_CHANGE = "RISK_CHANGE"
    TECHNICAL_CHANGE = "TECHNICAL_CHANGE"
    FUNDAMENTAL_CHANGE = "FUNDAMENTAL_CHANGE"


class MarketChangeEvent(Base):
    __tablename__ = "market_change_events"

    id = Column(Integer, primary_key=True)
    scan_run_id = Column(Integer, ForeignKey("market_scan_runs.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    change_type = Column(Enum(ChangeType), nullable=False, index=True)
    previous_value = Column(String(64), nullable=True)
    new_value = Column(String(64), nullable=True)
    delta = Column(Numeric(12, 4), nullable=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    scan_run = relationship("MarketScanRun")

    def __repr__(self) -> str:
        return f"<MarketChangeEvent symbol={self.symbol!r} change_type={self.change_type}>"
