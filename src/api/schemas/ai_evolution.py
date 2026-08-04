"""Response schemas for `/api/v1/admin/ai-evolution/*` -- the
staff-only Basirah Intelligence Dashboard (E9, Part 12 of the AI
Evolution Layer design). Every field here is sourced directly from an
already-persisted AI Evolution Layer table; no route computes a metric
live or fabricates a value not already stored.
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


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
