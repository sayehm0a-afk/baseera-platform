"""Basirah Radar V2 (2026-08-16), Phase B -- forward-testing foundation.

`RadarOpportunity` is the durable record of one thing Radar V2's
orchestrator actually emitted to a user: a Stage 1 candidate that
cleared bounded Stage 2 live validation and produced a real
`DecisionV2Snapshot`. Deliberately a thin table, not a duplicate of
Decision V2's own ~90-column shape: entry zone, targets, stop loss,
full reasoning, gates, and outcome tracking all already live on
`DecisionV2Snapshot`/`DecisionV2Outcome` (M10) and are reached here via
`decision_v2_snapshot_id` -- one row per emitted opportunity, one FK,
no re-derivation. What this table adds is what Decision V2 has no
concept of: Stage 1's local-only ranking (score, per-component
breakdown, which signals fired, and this candidate's rank within that
run's narrowed set) and the radar-level bookkeeping needed to answer
"why did this rank here" and "is this still the live call for this
symbol" without re-running anything.

`classification`/`classification_label_ar`/`confidence_score`/
`price_at_signal` are intentionally denormalized copies of the linked
snapshot's own `decision`/`decision_label_ar`/`confidence_score`/
`current_price` at emission time -- the same "denormalize the
frequently-filtered field" convention `decision_v2_snapshots.symbol`
already uses despite `stock_id` existing, so a radar summary/ranking
query never needs a join just to filter or sort.

Same append-only discipline as `DecisionV2Snapshot`/`DecisionV2Outcome`:
no UPDATE/DELETE from application code once written, except the one
narrow, structural exception below.

`superseded_by_id` is the one field ever written after insert, and
only to itself once, by the anti-flapping/dedup logic in Radar V2's
orchestrator (per the mandate: "Prevent duplicate/repeated
recommendations from dominating the radar unless new market evidence
materially changes the score."). A NULL `superseded_by_id` means this
row is still the live radar call for its symbol; a future scan that
finds materially the same evidence points this row at the new one
rather than emitting a fresh duplicate. The prior opportunity itself
is never edited beyond this one pointer -- its own score/evidence stay
exactly as emitted, so the history stays reproducible.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class RadarOpportunity(Base):
    __tablename__ = "radar_opportunities"
    __table_args__ = (
        UniqueConstraint("decision_v2_snapshot_id", name="uq_radar_opportunity_snapshot"),
    )

    id = Column(Integer, primary_key=True)
    symbol = Column(String(16), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)

    # The real, validated Decision V2 result this opportunity is built
    # from -- entry zone, targets, stop loss, full reasoning/gates,
    # and (via decision_v2_outcomes) later real-market outcome all live
    # there, not duplicated here.
    decision_v2_snapshot_id = Column(Integer, ForeignKey("decision_v2_snapshots.id"), nullable=False)

    # Plain Integer, not a real FK, matching decision_v2_snapshots.
    # scan_run_id's own established convention -- the "which radar run
    # produced this" grouping key.
    scan_run_id = Column(Integer, nullable=True, index=True)

    # Denormalized from the linked snapshot at emission time (see
    # module docstring) -- never re-derived, never drifts independently
    # of the snapshot it was copied from.
    classification = Column(String(32), nullable=False, index=True)
    classification_label_ar = Column(String(64), nullable=False)
    confidence_score = Column(Numeric(6, 2), nullable=False)
    price_at_signal = Column(Numeric(18, 4), nullable=True)

    # Stage 1's local-only ranking evidence for this candidate, in the
    # run that produced it -- see src.market_intelligence.
    # stage1_local_scan.Stage1SymbolResult, whose fields these mirror.
    stage1_rank = Column(Integer, nullable=True)
    stage1_ranking_score = Column(Numeric(6, 2), nullable=True)
    stage1_component_scores = Column(JSON, nullable=True)
    stage1_signals = Column(JSON, nullable=True)
    stage1_risk_reward_ratio = Column(Numeric(9, 4), nullable=True)

    # Short, human-readable explainability text: why this candidate
    # ranked where it did among its Stage 1 peers -- the mandate's
    # explicit "must be able to explain WHY this stock ranked above
    # other candidates" requirement.
    ranking_reason_ar = Column(Text, nullable=True)

    emitted_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Anti-flapping/dedup chain -- see module docstring. Self-FK, so a
    # superseded row's history stays queryable, never deleted.
    superseded_by_id = Column(Integer, ForeignKey("radar_opportunities.id"), nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock")
    snapshot = relationship("DecisionV2Snapshot")
    superseded_by = relationship("RadarOpportunity", remote_side=[id])

    def __repr__(self) -> str:
        return (
            f"<RadarOpportunity symbol={self.symbol!r} classification={self.classification!r} "
            f"emitted_at={self.emitted_at!r}>"
        )
