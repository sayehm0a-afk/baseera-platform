"""CommitteeAgentOpinion: one Investment Committee agent's structured
verdict on one live Decision Engine V2 decision -- the AI Multi-Agent
Investment Committee milestone. Distinct from `AgentOpinion` (E7's
panel, FK'd to `recommendation_snapshots.id`, the older V1/scan
pipeline): this table is FK'd to `decision_v2_snapshots.id`, the
canonical live `/decision-v2` decision, per the explicit requirement
that the committee integrate into the existing Decision Intelligence
Engine rather than remain a parallel system.

Insert-only, no unique constraint -- matches `DecisionV2Snapshot`'s own
append-only, multiple-rows-per-day pattern (unlike `AgentOpinion`,
whose parent `RecommendationSnapshot` is upserted once per symbol/day).
`evidence`/`rejection_reasons` are JSON lists of plain-text strings,
each sourced from a real, already-computed field -- never a fabricated
narrative (see `src.ai_evolution.committee.agents` for exactly how each
agent builds them).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base
from src.domain.models.agent_opinion import AgentStance


class CommitteeAgentOpinion(Base):
    __tablename__ = "committee_opinions"

    id = Column(Integer, primary_key=True)
    decision_v2_snapshot_id = Column(
        Integer, ForeignKey("decision_v2_snapshots.id"), nullable=False, index=True
    )

    agent_name = Column(String(64), nullable=False, index=True)
    agent_role = Column(String(32), nullable=False, index=True)
    stance = Column(Enum(AgentStance), nullable=False)
    confidence = Column(Numeric(6, 2), nullable=True)
    reasoning = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=True)
    rejection_reasons = Column(JSON, nullable=True)
    used_llm = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<CommitteeAgentOpinion decision_v2_snapshot_id={self.decision_v2_snapshot_id!r} "
            f"agent_name={self.agent_name!r} stance={self.stance}>"
        )
