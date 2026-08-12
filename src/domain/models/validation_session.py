"""M10: the durable record of one explicit, bounded live-market signal
validation run -- distinct from Basirah's routine scheduled scans,
which run continuously and are never validation evidence on their own.

A `ValidationSession` exists so every `DecisionV2Snapshot`/
`DecisionV2Outcome` row generated while it is open can be grouped,
reported on, and audited as belonging to one deliberate measurement
window, with the exact production commit and market context that was
in force at the time -- the reproducibility this milestone's "no
cherry-picking, no retrospective editing" principle depends on.

`is_dry_run` is a hard, separate flag (not folded into `status`) by
design: a dry run exercises the exact same code path as a real session
(so the pipeline itself is proven end-to-end), but its rows must never
be mistaken for real validation evidence merely because someone forgot
to check a status string. Every downstream metrics query must filter
on `is_dry_run == False` explicitly, never assume it.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class ValidationSessionStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    CLOSED = "CLOSED"
    ABORTED = "ABORTED"


class ValidationSession(Base):
    __tablename__ = "validation_sessions"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    status = Column(Enum(ValidationSessionStatus), nullable=False, default=ValidationSessionStatus.RUNNING, index=True)

    # Hard separation from real evidence -- see module docstring.
    is_dry_run = Column(Boolean, nullable=False, default=False, server_default="0", index=True)

    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Reproducibility (mandate Part E): the exact backend commit and a
    # free-form fingerprint of engine/gate versions in force for the
    # whole session -- every DecisionV2Snapshot issued under this
    # session inherits this via its validation_session_id FK, so it is
    # not duplicated per row.
    source_production_commit = Column(String(64), nullable=True)
    config_fingerprint = Column(JSON, nullable=True)

    # Part I: market regime snapshot captured once at session start
    # (TASI direction/change, breadth, liquidity, volatility, market
    # risk state, open/closed) -- never inferred if unavailable, only
    # ever the real values MarketBreadthSummary/classify_market_risk
    # produced at that moment.
    market_regime_at_start = Column(JSON, nullable=True)

    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<ValidationSession id={self.id} name={self.name!r} status={self.status} "
            f"is_dry_run={self.is_dry_run}>"
        )
