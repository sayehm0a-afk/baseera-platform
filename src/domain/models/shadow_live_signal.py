"""ShadowLiveSignal: the Shadow Mode audit ledger for Basirah's
recurrent live-scan scheduler (`src.market_intelligence.
recurrent_live_scan`) -- Phase 14 of the recurrent-live-intelligence
mandate ("BASIRAH -- PRODUCTION-GRADE RECURRENT LIVE MARKET
INTELLIGENCE").

Deliberately never read by any consumer-facing route or by
`src.market_intelligence.radar_v2` -- while Shadow Mode is active (the
only mode this table's writer supports; see recurrent_live_scan.py's
module docstring) a row here has ZERO effect on what a real user's
Radar/Watchlist/analysis page shows. `RadarOpportunity` stays the sole
source of the consumer feed, completely unmodified by this table's
existence. This is intentional isolation, not an oversight: the
mandate requires the actionable feed to remain byte-for-byte unchanged
until a human explicitly authorizes a later, separate PR to consume
this ledger.

Same relationship to `DecisionV2Snapshot` that `RadarOpportunity`
already has: every row here is built from one real, unmodified Decision
V2 evaluation (no new scoring/classification/threshold logic anywhere
in this module or its writer) -- `decision_v2_snapshot_id` is the
single source of truth for entry zone/targets/stop/reasoning/gates;
this table only adds the shadow-lifecycle interpretation of that
snapshot relative to whatever this symbol's own prior live shadow
signal said.

`superseded_by_id` is the exact same anti-flapping/append-only pattern
`RadarOpportunity.superseded_by_id` already established: NULL means
this row is still the current live shadow state for its symbol: at
most one such row should ever exist per symbol by construction. A row
is only ever written when Phase 9's material-change comparator found a
real difference worth recording (`UNCHANGED_SIGNAL` never produces a
row) -- so, unlike `RadarOpportunity`, there is no separate dedup-window
config; comparison is always against whichever row is currently live,
however old.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class ShadowLifecycleResult(str, enum.Enum):
    # A symbol reaching an actionable BUY-family Decision V2
    # classification for the first time in its live shadow history (no
    # prior live ShadowLiveSignal existed for it) -- the mandate's
    # headline acceptance case: "not actionable at 10:00, genuinely
    # qualified at 12:15."
    NEW_INTRADAY_OPPORTUNITY = "NEW_INTRADAY_OPPORTUNITY"
    # An existing live shadow signal's numbers moved materially
    # (classification/confidence/score/entry-zone/stop/target changed by
    # more than the existing radar_v2 dedup thresholds) while remaining
    # in the same broad actionable family.
    REFRESHED_SIGNAL = "REFRESHED_SIGNAL"
    # Decision V2's own entry_status is now EntryStatus.MISSED_ENTRY --
    # reused verbatim from the existing, unmodified Decision V2 output;
    # no new "missed" threshold computed here.
    MISSED_ENTRY = "MISSED_ENTRY"
    # The prior live signal was actionable BUY-family; Decision V2's
    # fresh evaluation downgraded it out of the BUY family (but entry_
    # status is not MISSED_ENTRY -- the engine still sees it as "close,
    # but the classification itself pulled back", e.g. anti-chase
    # already priced in by Decision V2 -- see PR #92) -- surfaced as a
    # distinct label from MISSED_ENTRY per the mandate's explicit
    # "CHASE_RISK or MISSED_ENTRY" acceptance wording.
    CHASE_RISK = "CHASE_RISK"
    # Decision V2's fresh evaluation rejected/exited the thesis outright
    # (decision in {REJECT, EXIT}) -- the strongest, most direct existing
    # signal that the setup no longer holds.
    INVALIDATED_SIGNAL = "INVALIDATED_SIGNAL"
    # A DERIVED, read-time-only state -- never returned by the
    # material-change classifier and never written as its own row
    # (there is no fresh DecisionV2Snapshot to anchor such a row to: by
    # construction, a symbol reaches STALE precisely because this cycle
    # did NOT re-evaluate it). Computed on read by comparing a live
    # row's own `decision_timestamp` against the operative trading
    # session via the existing, unmodified `src.analysis.decision_v2.
    # decision_freshness.classify_decision_freshness` -- see
    # recurrent_live_scan.py's `is_shadow_signal_stale`. Exists in this
    # enum only so callers have one shared vocabulary for "this shadow
    # row's own lifecycle state right now", covering both persisted
    # transitions and this one derived one.
    STALE_SIGNAL = "STALE_SIGNAL"
    # Returned by the classifier, never persisted as a row (Phase 9):
    # nothing about this symbol's shadow state changed materially this
    # cycle. Included in the enum only so the classifier has a total,
    # type-safe return value -- RecurrentScanCycle.signals_unchanged_
    # count is where this actually gets recorded.
    UNCHANGED_SIGNAL = "UNCHANGED_SIGNAL"


# Every member that DOES get written as a ShadowLiveSignal row.
# STALE_SIGNAL (derived at read time -- see its own docstring above)
# and UNCHANGED_SIGNAL (Phase 9: never persisted) are the two
# deliberate exceptions.
PERSISTED_LIFECYCLE_RESULTS = frozenset(
    {
        ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
        ShadowLifecycleResult.REFRESHED_SIGNAL,
        ShadowLifecycleResult.MISSED_ENTRY,
        ShadowLifecycleResult.CHASE_RISK,
        ShadowLifecycleResult.INVALIDATED_SIGNAL,
    }
)


class ShadowLiveSignal(Base):
    __tablename__ = "shadow_live_signals"

    id = Column(Integer, primary_key=True)

    # Plain, denormalized copy of the producing RecurrentScanCycle's own
    # cycle_id string -- deliberately NOT a ForeignKey, matching this
    # codebase's own established "scan_run_id is a plain Integer, not a
    # real FK" convention (see decision_v2_snapshots.scan_run_id /
    # radar_opportunities.scan_run_id): the cycle summary row is only
    # ever written AFTER every ShadowLiveSignal row it summarizes (its
    # own counts are derived from them), so there is no valid insert
    # order in which a real FK to recurrent_scan_cycles.id could be
    # satisfied at the time a ShadowLiveSignal row is written.
    cycle_id = Column(String(36), nullable=False, index=True)

    symbol = Column(String(16), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    decision_v2_snapshot_id = Column(Integer, ForeignKey("decision_v2_snapshots.id"), nullable=False, unique=True)

    lifecycle_result = Column(Enum(ShadowLifecycleResult), nullable=False, index=True)
    change_reason = Column(Text, nullable=True)

    # "ACTIVE_SIGNAL_REVALIDATION" (Phase 7 -- this symbol already had a
    # pending/live signal being re-checked) or "NEW_STAGE1_CANDIDATE"
    # (Phase 8 -- this symbol newly surfaced from Stage 1's ranked list
    # this cycle). Pure provenance metadata, never fed back into
    # selection or scoring.
    selection_reason = Column(String(32), nullable=True)

    # Denormalized from the linked snapshot at emission time, the same
    # convention RadarOpportunity's own columns already use -- plus the
    # "previous_*" companions a lifecycle ledger specifically needs, so
    # a reviewer can see the before/after without a second query.
    previous_classification = Column(String(32), nullable=True)
    classification = Column(String(32), nullable=False)
    previous_confidence_score = Column(Numeric(6, 2), nullable=True)
    confidence_score = Column(Numeric(6, 2), nullable=False)
    previous_entry_status = Column(String(32), nullable=True)
    entry_status = Column(String(32), nullable=True)
    previous_stage1_ranking_score = Column(Numeric(6, 2), nullable=True)
    stage1_ranking_score = Column(Numeric(6, 2), nullable=True)

    price_at_signal = Column(Numeric(18, 4), nullable=True)
    entry_zone_low = Column(Numeric(18, 4), nullable=True)
    entry_zone_high = Column(Numeric(18, 4), nullable=True)
    stop_loss = Column(Numeric(18, 4), nullable=True)
    target_1 = Column(Numeric(18, 4), nullable=True)
    target_2 = Column(Numeric(18, 4), nullable=True)
    target_3 = Column(Numeric(18, 4), nullable=True)
    risk_reward_target_1 = Column(Numeric(9, 4), nullable=True)

    data_freshness_status = Column(String(16), nullable=True)
    decision_timestamp = Column(DateTime(timezone=True), nullable=True)
    decision_engine_version = Column(String(32), nullable=True)

    emitted_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Anti-flapping/append-only chain -- identical convention to
    # RadarOpportunity.superseded_by_id (see module docstring).
    superseded_by_id = Column(Integer, ForeignKey("shadow_live_signals.id"), nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock")
    snapshot = relationship("DecisionV2Snapshot")
    superseded_by = relationship("ShadowLiveSignal", remote_side=[id])

    def __repr__(self) -> str:
        return (
            f"<ShadowLiveSignal symbol={self.symbol!r} lifecycle_result={self.lifecycle_result!r} "
            f"emitted_at={self.emitted_at!r}>"
        )
