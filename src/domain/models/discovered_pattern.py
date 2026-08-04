"""DiscoveredPattern: a durable record of one signal condition that
`src.ai_evolution.pattern_discovery` found to be statistically
associated with a significantly different win rate than the
population baseline -- E5 of the AI Evolution Layer.

Re-tested on a rolling basis (`PatternDiscoveryJob`, weekly), never
fire-and-forget: `still_valid` reflects only the most recent test, and
a pattern that stops holding up is marked `still_valid=False` rather
than deleted -- the append-only, fully-auditable discipline Part 11 of
the design applies to every AI Evolution Layer table.

Results here feed the existing `CalibrationEngine`'s weight proposals
and the analyst framework's explainability output -- never applied to
production weights or narration automatically by this table itself.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db.database import Base


class DiscoveredPattern(Base):
    __tablename__ = "discovered_patterns"
    __table_args__ = (
        UniqueConstraint(
            "condition_type", "condition_description", "evaluation_horizon_days",
            name="uq_discovered_pattern_identity",
        ),
    )

    id = Column(Integer, primary_key=True)

    # "signal_present" is the only condition_type this milestone tests
    # (see pattern_discovery.py's module docstring for why) -- a plain
    # string, not an enum, so a future condition type (an RSI range, a
    # MACD crossing) is additive, not a migration.
    condition_type = Column(String(32), nullable=False, index=True)
    condition_description = Column(String(255), nullable=False)
    evaluation_horizon_days = Column(Integer, nullable=False)

    sample_size = Column(Integer, nullable=False)
    win_rate = Column(Numeric(6, 4), nullable=False)
    baseline_win_rate = Column(Numeric(6, 4), nullable=False)
    z_score = Column(Numeric(9, 4), nullable=True)
    p_value = Column(Numeric(9, 6), nullable=True)

    still_valid = Column(Boolean, nullable=False, default=True)

    discovered_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_validated_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<DiscoveredPattern condition={self.condition_description!r} "
            f"win_rate={self.win_rate!r} still_valid={self.still_valid!r}>"
        )
