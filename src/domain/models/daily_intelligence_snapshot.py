"""DailyIntelligenceSnapshot: one day's pre-aggregated AI Evolution
Layer summary -- E9 (Part 12 of the design). The staff-only
Intelligence Dashboard reads these rows instead of computing live
aggregates on every page load, the same "engines compute, a thin
layer persists, routes only read" separation the rest of this
codebase already uses.

One row per `snapshot_date` (idempotent: re-running the aggregation
for an already-aggregated day updates that row rather than
duplicating it, the same convention `ReflectionReport.review_date`
already established). `market_regime_breakdown` is intentionally
absent: `RecommendationSnapshot.market_regime` is not populated by any
phase of this milestone (a disclosed gap since E1), so a regime
breakdown here would have to be fabricated -- omitted rather than
faked, not silently dropped without explanation.

Non-negotiable per Part 14 of the design: nothing in this table or its
aggregation ever excludes failed recommendations -- `failed_count` is
always computed and stored alongside `successful_count`, never behind
an opt-in flag.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, Integer, Numeric
from sqlalchemy.sql import func

from src.core.db.database import Base


class DailyIntelligenceSnapshot(Base):
    __tablename__ = "daily_intelligence_snapshots"

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, unique=True, index=True)

    recommendations_evaluated = Column(Integer, nullable=False)
    successful_count = Column(Integer, nullable=False)
    failed_count = Column(Integer, nullable=False)
    partial_count = Column(Integer, nullable=False)
    expired_count = Column(Integer, nullable=False)
    win_rate = Column(Numeric(6, 4), nullable=True)
    calibration_error = Column(Numeric(9, 6), nullable=True)

    # E7 agent panel activity that day (both 0/null when
    # AGENT_PANEL_ENABLED was off, or no scans ran -- an honest
    # reflection of the current system, not a bug).
    agent_panel_snapshot_count = Column(Integer, nullable=False, default=0)
    agent_debate_count = Column(Integer, nullable=False, default=0)
    agent_agreement_rate = Column(Numeric(6, 4), nullable=True)

    # Top/bottom `DiscoveredPattern` rows (E5) by win rate among those
    # currently `still_valid`, as of this snapshot -- [{"condition_description",
    # "win_rate", "sample_size", "p_value"}, ...], not recomputed here.
    best_patterns = Column(JSON, nullable=True)
    worst_patterns = Column(JSON, nullable=True)

    # {"Energy": {"count": int, "win_rate": float}, ...} over the same
    # terminal outcomes as `win_rate` above.
    sector_breakdown = Column(JSON, nullable=True)

    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<DailyIntelligenceSnapshot snapshot_date={self.snapshot_date!r} win_rate={self.win_rate!r}>"
