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


class ValidationSessionOut(BaseModel):
    """M10: one explicit, bounded live-market validation run. `is_dry_run`
    is always shown -- a dry-run session's evidence must never be mistaken
    for real validation evidence in any UI that renders this."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    is_dry_run: bool
    started_at: datetime
    ended_at: Optional[datetime] = None
    source_production_commit: Optional[str] = None
    market_regime_at_start: Optional[Dict] = None
    notes: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime


class ValidationSessionListOut(BaseModel):
    sessions: List[ValidationSessionOut]


class ValidationSessionCreateIn(BaseModel):
    name: str
    is_dry_run: bool = False
    notes: Optional[str] = None


class RankPerformanceOut(BaseModel):
    rank: int
    signal_count: int
    win_rate: Optional[float] = None
    average_return_pct: Optional[float] = None


class DuplicateSignalOut(BaseModel):
    symbol: str
    signal_count: int


class ValidationSessionMetricsOut(BaseModel):
    """M10 (Part G): every metric is computed live from this session's
    own `DecisionV2Snapshot`/`DecisionV2Outcome` rows -- see
    `src.ai_evolution.validation_metrics`. `DATA_UNAVAILABLE` is never
    folded into win_rate/false_positive_rate/stop_loss_rate."""

    validation_session_id: int

    total_signals_issued: int
    actionable_signals: int
    status_counts: Dict[str, int]

    win_rate: Optional[float] = None
    decisive_signal_count: int
    false_positive_rate: Optional[float] = None

    target_hit_rate_by_target: Dict[int, Optional[float]]
    stop_loss_rate: Optional[float] = None

    average_return_pct: Optional[float] = None
    expectancy_pct: Optional[float] = None

    average_time_to_target_days: Optional[float] = None
    average_time_to_stop_days: Optional[float] = None

    ranking_position_performance: List[RankPerformanceOut]

    calibration_pair_count: int
    expected_calibration_error: Optional[float] = None

    duplicate_signals: List[DuplicateSignalOut]
    duplicate_signal_rate: Optional[float] = None

    data_unavailable_count: int
    data_unavailable_rate: Optional[float] = None

    pending_count: int
    cancelled_count: int
    partial_count: int


class ValidationLedgerEntryOut(BaseModel):
    """M10: one row of the complete, immutable recommendation ledger for
    a validation session -- every field a reviewer needs to independently
    audit one recommendation and its real forward outcome, with nothing
    silently dropped or reclassified. `outcome_status` is null only for
    a non-actionable decision (WATCH/HOLD/etc.) that never opened a
    trackable position -- never for an actionable one, which always gets
    a row (PENDING at minimum)."""

    model_config = ConfigDict(from_attributes=True)

    decision_v2_snapshot_id: int
    symbol: str
    company_name_ar: Optional[str] = None
    decision_timestamp: datetime
    ranking_position: Optional[int] = None
    decision: str
    decision_label_ar: str
    confidence_score: float
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    current_price: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    stop_loss: Optional[float] = None
    expected_holding_period_min_days: Optional[int] = None
    expected_holding_period_max_days: Optional[int] = None
    expected_holding_period_label_ar: Optional[str] = None
    data_source: str
    is_real_data: Optional[bool] = None
    validation_session_id: Optional[int] = None

    outcome_status: Optional[str] = None
    outcome_due_at: Optional[datetime] = None
    entry_price: Optional[float] = None
    target_1_hit: Optional[bool] = None
    target_1_hit_at: Optional[datetime] = None
    target_2_hit: Optional[bool] = None
    target_2_hit_at: Optional[datetime] = None
    target_3_hit: Optional[bool] = None
    target_3_hit_at: Optional[datetime] = None
    stop_loss_hit: Optional[bool] = None
    stop_loss_hit_at: Optional[datetime] = None
    first_event: Optional[str] = None
    return_pct: Optional[float] = None
    time_to_target_days: Optional[int] = None
    time_to_stop_days: Optional[int] = None
    evaluated_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None


class ValidationLedgerOut(BaseModel):
    validation_session_id: int
    entries: List[ValidationLedgerEntryOut]
