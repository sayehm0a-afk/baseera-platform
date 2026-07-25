"""SymbolIntelligenceRecord: one symbol's result from one
MarketScanRun -- the Autonomous Market Intelligence Layer's "market
snapshot" granular data.

This is the single source of truth every ranking/watchlist/sector
aggregation reads from: rankings and watchlists are deliberately
*computed on read* from these rows (via
src.market_intelligence.ranking/watchlist), not persisted as their own
materialized tables -- they carry zero information this table doesn't
already have, so persisting them separately would just be a stale-prone
cache of this data, not a second source of truth. See
docs/MARKET_INTELLIGENCE.md for the full disclosure of this choice.

Reuses `RecommendationLabel` from recommendation_snapshot.py rather
than redefining the same five-value enum a third time (domain layer
already established this enum for exactly this purpose).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base
from src.domain.models.recommendation_snapshot import RecommendationLabel


class SymbolIntelligenceRecord(Base):
    __tablename__ = "symbol_intelligence_records"
    __table_args__ = (
        UniqueConstraint("scan_run_id", "stock_id", name="uq_symbol_intelligence_record_identity"),
    )

    id = Column(Integer, primary_key=True)
    scan_run_id = Column(Integer, ForeignKey("market_scan_runs.id"), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    sector = Column(String(128), nullable=True, index=True)

    recommendation = Column(Enum(RecommendationLabel), nullable=False)
    confidence = Column(Numeric(6, 2), nullable=False)
    final_score = Column(Numeric(6, 2), nullable=False)
    target_price = Column(Numeric(18, 4), nullable=True)
    stop_loss = Column(Numeric(18, 4), nullable=True)
    expected_return_pct = Column(Numeric(9, 4), nullable=True)
    risk_level = Column(String(16), nullable=True)
    time_horizon = Column(String(16), nullable=True)
    position_size = Column(String(16), nullable=True)

    technical_score = Column(Numeric(6, 2), nullable=True)
    fundamental_score = Column(Numeric(6, 2), nullable=True)
    dividend_yield = Column(Numeric(9, 6), nullable=True)
    rsi = Column(Numeric(6, 2), nullable=True)
    adx = Column(Numeric(6, 2), nullable=True)
    latest_price = Column(Numeric(18, 4), nullable=True)
    bollinger_upper = Column(Numeric(18, 4), nullable=True)

    bullish_factors = Column(JSON, nullable=True)
    bearish_factors = Column(JSON, nullable=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    engine_version = Column(String(32), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    scan_run = relationship("MarketScanRun")
    stock = relationship("Stock")

    def __repr__(self) -> str:
        return f"<SymbolIntelligenceRecord symbol={self.symbol!r} scan_run_id={self.scan_run_id} recommendation={self.recommendation}>"
