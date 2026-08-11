"""Response schemas for `/api/v1/admin/ai-evolution/*` -- the
staff-only Basirah Intelligence Dashboard (E9, Part 12 of the AI
Evolution Layer design). Every field here is sourced directly from an
already-persisted AI Evolution Layer table; no route computes a metric
live or fabricates a value not already stored.
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class GroupPerformanceOut(BaseModel):
    group: str
    sample_size: int
    win_rate: Optional[float] = None


class PersonalPerformanceDashboardOut(BaseModel):
    """OWNER-only diagnostic dashboard over the personal day-trading
    product's own real decisions and outcomes (CONT Phase 3) -- distinct
    from the public `/api/v1/recommendations/history/stats` track
    record, which is intentionally open to every user. Every metric is
    `None`/empty with `insufficient_data_message_ar` set rather than a
    fabricated figure when the underlying sample is empty."""

    generated_at: datetime
    evaluation_horizon_days: int

    total_decisions_issued: int
    decision_distribution: Dict[str, int]
    entry_status_distribution: Dict[str, int]
    market_risk_state_distribution: Dict[str, int]
    sector_distribution: Dict[str, int]

    outcome_sample_size: int
    terminal_outcome_sample_size: int
    status_counts: Dict[str, int]
    target_1_hit_rate: Optional[float] = None
    target_2_hit_rate: Optional[float] = None
    target_3_hit_rate: Optional[float] = None
    stop_loss_hit_rate: Optional[float] = None
    expired_count: int
    unresolved_count: int
    average_max_favorable_excursion_pct: Optional[float] = None
    average_max_adverse_excursion_pct: Optional[float] = None
    average_realized_return_pct: Optional[float] = None
    average_time_to_target_days: Optional[float] = None

    calibration_by_bucket: Optional[Dict] = None
    calibration_by_type: Dict[str, Dict]
    calibration_by_holding_period: Dict[str, Dict]
    calibration_by_sector: Dict[str, Dict]
    market_risk_state_calibration_unavailable_ar: str

    strongest_groups: List[GroupPerformanceOut]
    weakest_groups: List[GroupPerformanceOut]

    small_sample_warning: bool
    insufficient_data_message_ar: Optional[str] = None


class DailyIntelligenceSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_date: date
    recommendations_evaluated: int
    successful_count: int
    failed_count: int
    partial_count: int
    expired_count: int
    win_rate: Optional[float] = None
    calibration_error: Optional[float] = None
    agent_panel_snapshot_count: int
    agent_debate_count: int
    agent_agreement_rate: Optional[float] = None
    best_patterns: Optional[List[Dict]] = None
    worst_patterns: Optional[List[Dict]] = None
    sector_breakdown: Optional[Dict] = None
    computed_at: datetime


class CalibrationStatusOut(BaseModel):
    """Side by side status of both distinct "calibration" concepts
    this platform has (see `ConfidenceCalibrationModel`'s module
    docstring for why they're kept separate): contributor-WEIGHT
    calibration (`CalibrationConfig`) and confidence-probability
    calibration (`ConfidenceCalibrationModel`). Plus E8's paper-trading
    challenger, if one is currently eligible."""

    active_weight_calibration_version: Optional[str] = None
    active_weight_calibration_activated_at: Optional[datetime] = None
    active_confidence_calibration_version: Optional[str] = None
    active_confidence_calibration_method: Optional[str] = None
    active_confidence_calibration_activated_at: Optional[datetime] = None
    latest_validated_challenger_version: Optional[str] = None


class DiscoveredPatternOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    condition_type: str
    condition_description: str
    evaluation_horizon_days: int
    sample_size: int
    win_rate: float
    baseline_win_rate: float
    z_score: Optional[float] = None
    p_value: Optional[float] = None
    still_valid: bool
    discovered_at: datetime
    last_validated_at: datetime


class DiscoveredPatternListOut(BaseModel):
    patterns: List[DiscoveredPatternOut]


class ReflectionReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_date: date
    recommendations_reviewed: int
    successful_count: int
    failed_count: int
    partial_count: int
    expired_count: int
    win_rate: Optional[float] = None
    key_findings: List[str]
    improvement_suggestions: List[str]
    generated_at: datetime


class ReflectionReportListOut(BaseModel):
    reports: List[ReflectionReportOut]


class PaperTradeComparisonOut(BaseModel):
    evaluation_horizon_days: int
    champion_sample_size: int
    champion_win_rate: Optional[float] = None
    challenger_sample_size: int
    challenger_win_rate: Optional[float] = None
    z_score: Optional[float] = None
    p_value: Optional[float] = None
    significant: bool
