"""UserFollowedSignal: a user's explicit, one-tap commitment to a
specific real BUY recommendation ("متابعة هذه الإشارة") -- product
decision 2026-09-18, following the owner's request for a personal-
performance feature comparable to competitor apps.

This is deliberately NOT the same concept as `UserWatchlist` (a
standing list of symbols to keep an eye on). Following a signal
snapshots the caller's intent to act on ONE specific, already-issued
`DecisionV2Snapshot` at the moment they saw it, so its real outcome
(already tracked independently by `DecisionV2Outcome` -- see
src.ai_evolution.decision_v2_outcome_evaluation) can later be counted
as one of "this user's own calls" rather than folded into the
algorithm's aggregate track record. No target/stop/outcome data is
duplicated here; this table only records WHICH decisions a user chose
to follow and WHEN, and every performance number is computed by
joining out to `DecisionV2Outcome` at read time (see
src.market_intelligence.followed_signals) so a followed signal's
displayed status can never drift from the one real, already-audited
outcome record.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class UserFollowedSignal(Base):
    __tablename__ = "user_followed_signals"
    __table_args__ = (
        UniqueConstraint("user_id", "decision_v2_snapshot_id", name="uq_user_followed_signal_snapshot"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_v2_snapshot_id = Column(
        Integer, ForeignKey("decision_v2_snapshots.id"), nullable=False, index=True
    )
    # Denormalized for cheap listing without a join, matching
    # UserWatchlistItem.symbol's existing pattern.
    symbol = Column(String(16), nullable=False, index=True)

    followed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    snapshot = relationship("DecisionV2Snapshot")

    def __repr__(self) -> str:
        return (
            f"<UserFollowedSignal user_id={self.user_id!r} "
            f"decision_v2_snapshot_id={self.decision_v2_snapshot_id!r} symbol={self.symbol!r}>"
        )
