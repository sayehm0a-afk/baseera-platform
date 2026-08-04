"""AgentOpinion: one panel member's structured opinion on one live
recommendation -- E7 of the AI Evolution Layer. Every recommendation
that runs the panel gets one row per agent (Technical/Fundamental/
Risk/Quant/Macro/News/Sentiment); `used_llm` distinguishes the two
(News, Sentiment) that made a real, grounded LLM call from the rest,
which are structured wrappers over already-deterministic engine
output. `reasoning` is always plain text sourced from real computed
data (a contributor's category/points/notes, or -- for News/Sentiment
-- a grounded LLM rephrasing that can never introduce a number absent
from its own prompt); never a fabricated narrative.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class AgentStance(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNAVAILABLE = "UNAVAILABLE"  # the agent had no data for this recommendation (e.g. Macro Analyst, always)


class AgentOpinion(Base):
    __tablename__ = "agent_opinions"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("recommendation_snapshots.id"), nullable=False, index=True)

    agent_name = Column(String(64), nullable=False, index=True)
    stance = Column(Enum(AgentStance), nullable=False)
    confidence = Column(Numeric(6, 2), nullable=True)
    reasoning = Column(Text, nullable=False)
    used_llm = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AgentOpinion snapshot_id={self.snapshot_id!r} agent_name={self.agent_name!r} stance={self.stance}>"
