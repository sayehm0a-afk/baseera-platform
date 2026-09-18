"""POST/GET/DELETE /api/v1/signals -- a user's explicit "follow this
signal" commitments to specific real BUY recommendations, and the
honest personal-vs-algorithm win-rate comparison computed from their
real, already-tracked outcomes (see
src.market_intelligence.followed_signals).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FollowSignalRequest(BaseModel):
    decision_v2_snapshot_id: int


class FollowedSignalOut(BaseModel):
    id: int
    decision_v2_snapshot_id: int
    symbol: str
    company_name_ar: Optional[str] = None
    followed_at: datetime

    decision: str
    decision_label_ar: str
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None

    # Real, already-tracked outcome for this exact snapshot -- null
    # only when no DecisionV2Outcome row exists yet (never fabricated).
    outcome_status: Optional[str] = None
    outcome_status_label_ar: Optional[str] = None
    outcome_return_pct: Optional[float] = None


class FollowedSignalListOut(BaseModel):
    generated_at: datetime
    items: List[FollowedSignalOut] = Field(default_factory=list)


class PersonalPerformanceComparisonOut(BaseModel):
    generated_at: datetime

    personal_resolved_sample_size: int
    personal_win_rate_pct: Optional[float] = None
    personal_small_sample_warning: bool

    algorithm_resolved_sample_size: int
    algorithm_win_rate_pct: Optional[float] = None

    insufficient_data_message_ar: Optional[str] = None
