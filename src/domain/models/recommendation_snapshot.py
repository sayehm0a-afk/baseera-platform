"""Historical AI-decision snapshot model -- the durable audit record
one BacktestingEngine evaluation (or, in the future, a live production
decision) writes so it can be reproduced and scored later.

Deliberately domain-local, not importing anything from src.analysis --
the domain layer has no dependency on the analysis layer anywhere else
in this codebase (loaders go the other direction: analysis depends on
domain), and this model keeps that direction intact. `RecommendationLabel`
mirrors src.analysis.recommendation.types.Recommendation's five string
values without importing it, the same relationship PeriodType/Timeframe
already have to their own domains.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
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


class RecommendationLabel(str, enum.Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class RecommendationSnapshot(Base):
    """One point-in-time AI decision, frozen for later audit/scoring.

    `symbol` is denormalized (also reachable via `stock`) so a
    snapshot's identity survives a later rename of the Stock row it
    was evaluated against -- an audit record must describe the world
    as it was, not as it is now. `run_id` is nullable because a
    snapshot's origin need not always be a BacktestingEngine run (a
    future live-production decision log could reuse this same table),
    but every snapshot this milestone writes does have one.

    The unique constraint on (run_id, stock_id, evaluated_at) is what
    makes re-running the same backtest idempotent -- re-evaluating an
    already-evaluated (run, symbol, date) upserts in place instead of
    accumulating duplicate rows.
    """

    __tablename__ = "recommendation_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "stock_id", "evaluated_at", name="uq_recommendation_snapshot_identity"),
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    market_price_at_evaluation = Column(Numeric(18, 4), nullable=True)

    recommendation = Column(Enum(RecommendationLabel), nullable=False)
    total_score = Column(Numeric(6, 2), nullable=False)
    confidence_score = Column(Numeric(6, 2), nullable=False)

    technical_score = Column(Numeric(6, 2), nullable=True)
    fundamental_score = Column(Numeric(6, 2), nullable=True)
    momentum_score = Column(Numeric(6, 2), nullable=True)
    volume_score = Column(Numeric(6, 2), nullable=True)
    risk_score = Column(Numeric(6, 2), nullable=True)
    # Full per-contributor breakdown (source, points, weight, confidence,
    # available, notes) for every contributor that ran, including
    # whichever external-factor modules (news/macro/insider/sector
    # rotation) had data available -- the five named *_score columns
    # above are a convenience for the common/always-present modules;
    # this JSON blob is the complete, reproducible record.
    contributor_breakdown = Column(JSON, nullable=True)
    signals = Column(JSON, nullable=True)
    reasons = Column(JSON, nullable=True)

    target_price = Column(Numeric(18, 4), nullable=True)
    stop_loss = Column(Numeric(18, 4), nullable=True)
    expected_return_pct = Column(Numeric(9, 4), nullable=True)
    time_horizon = Column(String(16), nullable=True)
    risk_level = Column(String(16), nullable=True)
    position_size = Column(String(16), nullable=True)

    # Provenance / anti-look-ahead audit trail -- exactly what data this
    # decision was allowed to see, and where the price it was scored
    # against came from.
    technical_input_as_of = Column(DateTime(timezone=True), nullable=True)
    fundamental_input_as_of = Column(Date, nullable=True)
    price_bar_source = Column(String(64), nullable=True)
    price_bar_is_synthetic = Column(Boolean, nullable=True)

    engine_version = Column(String(32), nullable=False)
    calibration_version = Column(String(64), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock")
    run = relationship("BacktestRun", back_populates="snapshots")

    def __repr__(self) -> str:
        return (
            f"<RecommendationSnapshot symbol={self.symbol!r} evaluated_at={self.evaluated_at!r} "
            f"recommendation={self.recommendation}>"
        )
