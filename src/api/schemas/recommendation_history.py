"""GET /api/v1/recommendations/history[/stats] and
GET /api/v1/admin/recommendation-history -- the platform's real,
append-only recommendation track record. Every field is a direct read
of RecommendationSnapshot/RecommendationOutcome (src.domain.models) --
no recomputation, no fabricated statistic, and nothing is ever
filtered out by default (Part 11/12 of the AI Evolution Layer design:
failed/rejected recommendations are never hidden).
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RecommendationOutcomeOut(BaseModel):
    evaluation_horizon_days: int
    status: str
    due_at: datetime
    evaluated_at: Optional[datetime] = None
    price_at_evaluation: Optional[float] = None
    return_pct: Optional[float] = None
    hit_target: Optional[bool] = None
    hit_stop: Optional[bool] = None
    target_1_reached: Optional[bool] = None
    target_1_reached_at: Optional[datetime] = None
    target_2_reached: Optional[bool] = None
    target_2_reached_at: Optional[datetime] = None
    target_3_reached: Optional[bool] = None
    target_3_reached_at: Optional[datetime] = None
    max_favorable_excursion_pct: Optional[float] = None
    max_adverse_excursion_pct: Optional[float] = None
    time_to_target_days: Optional[int] = None


class RecommendationHistoryItemOut(BaseModel):
    id: int
    symbol: str
    company_name_ar: Optional[str] = None
    sector: Optional[str] = None

    evaluated_at: datetime
    recommendation: str
    confidence_score: float
    calibrated_confidence_score: Optional[float] = None

    market_price_at_evaluation: Optional[float] = None
    target_price: Optional[float] = None
    target_price_2: Optional[float] = None
    target_price_3: Optional[float] = None
    stop_loss: Optional[float] = None
    expected_return_pct: Optional[float] = None
    time_horizon: Optional[str] = None
    risk_level: Optional[str] = None
    position_size: Optional[str] = None
    expires_at: Optional[datetime] = None

    reasons: List[str] = Field(default_factory=list)
    engine_version: str
    is_paper_trade: Optional[bool] = None

    # ACTIVE: not expired, at least one outcome still PENDING.
    # COMPLETED: every issued outcome has reached a terminal status.
    # EXPIRED: past expires_at with outcomes still PENDING.
    # NO_OUTCOMES_TRACKED: no RecommendationOutcome rows exist yet (a
    # genuine "not yet" state, not an error -- see create_pending_outcomes).
    overall_status: str
    outcomes: List[RecommendationOutcomeOut] = Field(default_factory=list)


class RecommendationHistoryListOut(BaseModel):
    generated_at: datetime
    total: int
    items: List[RecommendationHistoryItemOut]


class RecommendationHistoryAuditItemOut(RecommendationHistoryItemOut):
    """Staff-only extension of the public history item -- adds the raw
    internal fields (per-contributor score breakdown, raw signals,
    which calibration model version was active) an operator needs to
    audit *why* a recommendation was made, never shown to ordinary
    users."""

    contributor_breakdown: Optional[list] = None
    signals: Optional[list] = None
    total_score: Optional[float] = None
    calibration_version: Optional[str] = None
    run_id: Optional[int] = None
    source: Optional[str] = None


class RecommendationHistoryAuditListOut(BaseModel):
    generated_at: datetime
    total: int
    items: List[RecommendationHistoryAuditItemOut]


class RecommendationHistoryStatsOut(BaseModel):
    """Aggregate performance over one evaluation horizon at a time --
    never blended across horizons, since a 1-day and a 90-day outcome
    answer different questions. `sample_size` is always shown alongside
    every percentage so a tiny sample can never be mistaken for a
    reliable track record."""

    generated_at: datetime
    evaluation_horizon_days: int
    sample_size: int
    terminal_sample_size: int
    win_rate: Optional[float] = None
    average_return_pct: Optional[float] = None
    target_hit_rate: Optional[float] = None
    stop_hit_rate: Optional[float] = None
    status_counts: Dict[str, int] = Field(default_factory=dict)
    small_sample_warning: bool = False
