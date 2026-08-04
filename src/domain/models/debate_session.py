"""DebateSession: the durable record of one multi-agent debate --
only created when `src.ai_evolution.agents.conflict` detects material
disagreement between agent opinions on a live recommendation (E7 of
the AI Evolution Layer), never on every recommendation, to bound LLM
cost. At most one per snapshot -- most snapshots will have none at
all, which is the expected, honest state (most recommendations don't
have material disagreement to debate).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db.database import Base


class DebateSession(Base):
    __tablename__ = "debate_sessions"
    __table_args__ = (UniqueConstraint("snapshot_id", name="uq_debate_session_snapshot"),)

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("recommendation_snapshots.id"), nullable=False, index=True)

    participants = Column(JSON, nullable=False)  # list of agent names that took part
    rounds = Column(Integer, nullable=False)
    agreement_level = Column(Numeric(6, 4), nullable=True)  # DebateEngine.detect_consensus()'s consensus score
    final_decision = Column(String(16), nullable=True)  # VotingSystem's winning option, if any

    # The one real LLM call in a debate: the Judge Agent's grounded
    # synthesis of why the panel reached this outcome. Empty string
    # (never a fabricated fallback) if the LLM call failed or was
    # rejected as ungrounded -- the structured fields above always
    # stand on their own regardless.
    judge_explanation = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<DebateSession snapshot_id={self.snapshot_id!r} final_decision={self.final_decision!r}>"
