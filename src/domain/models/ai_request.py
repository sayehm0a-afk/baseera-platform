"""AIRequest: one record per LLM call, for the Admin Dashboard's "view
AI usage" and per-user cost/usage accounting. `user_id` is nullable
because not every AI call in this codebase is triggered by a logged-in
user's request today (e.g. a scheduled market-intelligence scan) --
recorded anyway for aggregate usage/cost visibility. Instrumented at
the call sites in src/analysis/analyst/analyst_engine.py,
src/analysis/recommendation/recommendation_engine.py, and
src/analysis/decision/ai_decision_engine.py (Phase 10 M10.8), not
inside OpenAILLMClient itself, which has no concept of "which
user/feature" this call is for.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from src.core.db.database import Base


class AIRequestStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class AIRequest(Base):
    __tablename__ = "ai_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    feature = Column(String(100), nullable=False, index=True)
    symbol = Column(String(20), nullable=True)
    model = Column(String(100), nullable=True)

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    latency_ms = Column(Float, nullable=True)
    status = Column(Enum(AIRequestStatus), nullable=False)
    error_message = Column(Text, nullable=True)
    estimated_cost_usd = Column(Numeric(10, 6), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AIRequest id={self.id} feature={self.feature!r} status={self.status}>"
