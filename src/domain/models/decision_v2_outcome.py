"""M10: the durable outcome record for one `DecisionV2Snapshot` --
whether the entry/target/stop it published against real Saudi market
prices actually resolved, and how. One row per snapshot (unlike
`RecommendationOutcome`'s one-row-per-fixed-horizon design): Decision
V2 already carries its own `expected_holding_period_max_days` per
decision, so `due_at` is derived per-row from that instead of being
evaluated at several fixed checkpoints. The row is created PENDING at
issuance and re-evaluated on every scheduler pass against all real
price data available so far -- it moves to a terminal status the
first time a real touch is observed, not only once the full horizon
has elapsed, so a target hit on day 2 is reported on day 2, not held
back until day 30.

Only created for an actionable BUY-like decision
(STRONG_BUY_CANDIDATE/BUY_CANDIDATE) -- WATCH/HOLD/WAIT_FOR_ENTRY/
REJECT/etc. open no position, so there is nothing for target/stop
tracking to judge; those decisions are counted directly from
`DecisionV2Snapshot.decision` in the M10 metrics module instead.

Same append-only discipline as `RecommendationOutcome`/
`AuditLog`: no UPDATE/DELETE from application code once a terminal
status is reached; a correction, if one is ever genuinely needed,
must be a new linked row, not an edit of this one.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
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


class DecisionV2OutcomeStatus(str, enum.Enum):
    PENDING = "PENDING"
    TARGET_1_HIT = "TARGET_1_HIT"
    TARGET_2_HIT = "TARGET_2_HIT"
    TARGET_3_HIT = "TARGET_3_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    # Reserved for the one genuinely ambiguous case daily OHLC data
    # cannot resolve: a target and the stop both touched on the same
    # bar, so which happened first intraday is unknowable -- never
    # guessed, always disclosed as PARTIAL rather than picked either way.
    PARTIAL = "PARTIAL"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    # Real forward price data was never obtainable for this symbol
    # within the grace window -- NOT a loss, NOT a win, must be
    # excluded from win-rate/false-positive-rate math everywhere it is
    # computed (see src/ai_evolution/validation_metrics.py).
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    # BASIRAH LIVE VALIDATION TRACKING: price never traded into
    # entry_zone_low..entry_zone_high before the horizon (due_at)
    # elapsed -- no position was ever opened, so this is neither a win
    # nor a loss. Distinct from PENDING (still might trigger) and from
    # EXPIRED (which, after this change, only applies to a position
    # that DID enter and then ran out the clock without hitting target
    # or stop).
    ENTRY_NEVER_TRIGGERED = "ENTRY_NEVER_TRIGGERED"
    # The setup died before the entry zone was ever reached: price
    # closed at/through stop_loss while still pre-entry. Distinct from
    # STOP_LOSS_HIT, which by definition only fires after entry_
    # triggered=True -- a pre-entry stop-level touch was never a real
    # position, so it is not counted as a loss.
    INVALIDATED = "INVALIDATED"


# Never scored as a win or a loss by any M10 metric -- kept as a single
# named constant so every metrics function excludes the same set.
NON_RESOLVING_STATUSES = frozenset(
    {
        DecisionV2OutcomeStatus.PENDING,
        DecisionV2OutcomeStatus.CANCELLED,
        DecisionV2OutcomeStatus.DATA_UNAVAILABLE,
        DecisionV2OutcomeStatus.ENTRY_NEVER_TRIGGERED,
        DecisionV2OutcomeStatus.INVALIDATED,
    }
)


class DecisionV2Outcome(Base):
    __tablename__ = "decision_v2_outcomes"
    __table_args__ = (
        UniqueConstraint("decision_v2_snapshot_id", name="uq_decision_v2_outcome_snapshot"),
    )

    id = Column(Integer, primary_key=True)
    decision_v2_snapshot_id = Column(
        Integer, ForeignKey("decision_v2_snapshots.id"), nullable=False, index=True
    )
    validation_session_id = Column(Integer, ForeignKey("validation_sessions.id"), nullable=True, index=True)
    symbol = Column(String(16), nullable=False, index=True)

    due_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(
        Enum(DecisionV2OutcomeStatus), nullable=False, default=DecisionV2OutcomeStatus.PENDING, index=True
    )

    # Populated only once price actually trades into entry_zone_low..
    # entry_zone_high (see BASIRAH LIVE VALIDATION TRACKING below);
    # target/stop/excursion tracking never begins before this is True.
    # `entry_price` is set to entry_zone_high (the least favorable real
    # fill inside the recommended zone, a disclosed conservative
    # assumption -- daily OHLC cannot reveal the exact intraday fill)
    # at the same moment entry_triggered flips True.
    entry_triggered = Column(Boolean, nullable=False, default=False, server_default="0")
    entry_triggered_at = Column(DateTime(timezone=True), nullable=True)
    entry_price = Column(Numeric(18, 4), nullable=True)

    # True only for the pre-entry INVALIDATED case (see status enum) --
    # the setup died before ever becoming a real position.
    invalidated = Column(Boolean, nullable=False, default=False, server_default="0")
    invalidated_at = Column(DateTime(timezone=True), nullable=True)

    # Raw post-entry price extremes (literal, not just the pct-based
    # MFE/MAE below) -- computed once entry_triggered=True, over the
    # window starting at entry_triggered_at.
    highest_price_after_entry = Column(Numeric(18, 4), nullable=True)
    lowest_price_after_entry = Column(Numeric(18, 4), nullable=True)

    first_price_after_signal = Column(Numeric(18, 4), nullable=True)
    first_price_after_signal_at = Column(DateTime(timezone=True), nullable=True)

    target_1_hit = Column(Boolean, nullable=True)
    target_1_hit_at = Column(DateTime(timezone=True), nullable=True)
    target_2_hit = Column(Boolean, nullable=True)
    target_2_hit_at = Column(DateTime(timezone=True), nullable=True)
    target_3_hit = Column(Boolean, nullable=True)
    target_3_hit_at = Column(DateTime(timezone=True), nullable=True)
    stop_loss_hit = Column(Boolean, nullable=True)
    stop_loss_hit_at = Column(DateTime(timezone=True), nullable=True)

    # "TARGET" | "STOP" | "TIE" (same-bar, undecidable) -- which of the
    # target/stop family was touched first in real time, null while
    # PENDING or if the horizon expired with neither touched.
    first_event = Column(String(8), nullable=True)

    max_favorable_excursion_pct = Column(Numeric(9, 4), nullable=True)
    max_adverse_excursion_pct = Column(Numeric(9, 4), nullable=True)

    end_of_session_price = Column(Numeric(18, 4), nullable=True)
    next_session_price = Column(Numeric(18, 4), nullable=True)

    price_at_expected_duration = Column(Numeric(18, 4), nullable=True)
    return_pct_at_expected_duration = Column(Numeric(9, 4), nullable=True)

    # Final realized return once a terminal status is reached: the
    # target/stop price itself for a HIT, the last available close for
    # EXPIRED -- never populated for PENDING/CANCELLED/DATA_UNAVAILABLE.
    return_pct = Column(Numeric(9, 4), nullable=True)

    time_to_target_days = Column(Integer, nullable=True)
    time_to_stop_days = Column(Integer, nullable=True)

    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    snapshot = relationship("DecisionV2Snapshot")

    def __repr__(self) -> str:
        return (
            f"<DecisionV2Outcome snapshot_id={self.decision_v2_snapshot_id!r} "
            f"symbol={self.symbol!r} status={self.status}>"
        )
