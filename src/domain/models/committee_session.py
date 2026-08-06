"""CommitteeConsensus: the durable record of the Investment Committee's
consensus over one live Decision Engine V2 decision -- weighted vote
outcome, agreement/disagreement, most optimistic/conservative agent,
and the rejected-alternatives explanation, computed by
`src.ai_evolution.committee.consensus.build_consensus`.

Exactly one row per `DecisionV2Snapshot` (unique constraint) -- unlike
`CommitteeAgentOpinion` (one row per agent per decision), there is only
ever one consensus per decision. Distinct from the older
`DebateSession` (E7, FK'd to `recommendation_snapshots.id`, created
only when tension between two categories crosses a threshold): this
row is written for every committee run, since the mandate requires
"every recommendation is produced through independent expert analysis
before a final consensus," not only the disputed ones.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db.database import Base


class CommitteeConsensus(Base):
    __tablename__ = "committee_sessions"
    __table_args__ = (UniqueConstraint("decision_v2_snapshot_id", name="uq_committee_session_snapshot"),)

    id = Column(Integer, primary_key=True)
    decision_v2_snapshot_id = Column(
        Integer, ForeignKey("decision_v2_snapshots.id"), nullable=False, index=True
    )

    final_decision = Column(String(16), nullable=False)  # "BUY" | "SELL" | "HOLD"
    final_confidence = Column(Numeric(6, 2), nullable=False)

    participant_count = Column(Integer, nullable=False)
    directional_count = Column(Integer, nullable=False)
    agreement_pct = Column(Numeric(6, 2), nullable=False)
    disagreement_pct = Column(Numeric(6, 2), nullable=False)
    disagreement_score = Column(Numeric(6, 2), nullable=False)

    most_optimistic_agent = Column(String(64), nullable=True)
    most_optimistic_stance = Column(String(16), nullable=True)
    most_conservative_agent = Column(String(64), nullable=True)
    most_conservative_stance = Column(String(16), nullable=True)

    consensus_reasoning_ar = Column(Text, nullable=False)

    # List of {agent_name, stance, confidence, reasoning, rejection_reason}
    # dicts -- every dissenting agent's opinion and why it was outweighed.
    rejected_alternatives = Column(JSON, nullable=True)
    # {agent_name: weighted_vote_contribution} -- the real weighted-voting
    # arithmetic behind final_decision, not a summary re-derivation.
    weighted_votes = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<CommitteeConsensus decision_v2_snapshot_id={self.decision_v2_snapshot_id!r} "
            f"final_decision={self.final_decision!r} agreement_pct={self.agreement_pct!r}>"
        )
