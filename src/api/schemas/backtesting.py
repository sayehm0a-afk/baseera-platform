"""Request/response schemas for /api/v1/backtests and
/api/v1/calibrations. Bounded-workload limits (Phase 7) are enforced
here via `model_validator`s that call src.backtesting.config's
functions at validation time (not at class-definition time), so tests
can monkeypatch the underlying env vars the same way
src.market_data.ingestion.config's own callers already do.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.backtesting.config import get_max_backtest_range_days, get_max_backtest_symbols

_VALID_PROVENANCE_MODES = {"SYNTHETIC", "LIVE"}
_VALID_RECOMMENDATION_THRESHOLDS = {"BUY", "SELL"}


class BacktestCreateRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1)
    start_date: date
    end_date: date
    data_provenance_mode: str = "SYNTHETIC"
    strategy: str = "ai_decision_engine"
    evaluation_frequency_days: int = Field(default=7, ge=1, le=365)
    holding_horizon_days: int = Field(default=20, ge=1, le=730)
    target_price_horizon_days: int = Field(default=60, ge=1, le=730)
    transaction_cost_bps: float = Field(default=0.0, ge=0, le=1000)
    slippage_bps: float = Field(default=0.0, ge=0, le=1000)
    confidence_threshold: Optional[float] = Field(default=None, ge=0, le=100)
    recommendation_threshold: Optional[str] = None
    fundamental_reporting_lag_days: int = Field(default=45, ge=0, le=365)
    calibration_version: Optional[str] = None

    @field_validator("symbols")
    @classmethod
    def _normalize_symbols(cls, value: List[str]) -> List[str]:
        deduped = list(dict.fromkeys(s.strip() for s in value if s.strip()))
        if not deduped:
            raise ValueError("symbols must contain at least one non-empty symbol")
        if len(deduped) > get_max_backtest_symbols():
            raise ValueError(f"symbols exceeds the maximum of {get_max_backtest_symbols()} per backtest")
        return deduped

    @field_validator("data_provenance_mode")
    @classmethod
    def _validate_provenance_mode(cls, value: str) -> str:
        if value not in _VALID_PROVENANCE_MODES:
            raise ValueError(f"data_provenance_mode must be one of {sorted(_VALID_PROVENANCE_MODES)}")
        return value

    @field_validator("recommendation_threshold")
    @classmethod
    def _validate_recommendation_threshold(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in _VALID_RECOMMENDATION_THRESHOLDS:
            raise ValueError(f"recommendation_threshold must be one of {sorted(_VALID_RECOMMENDATION_THRESHOLDS)} or omitted")
        return value

    @model_validator(mode="after")
    def _validate_date_range(self) -> "BacktestCreateRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        span = (self.end_date - self.start_date).days
        max_days = get_max_backtest_range_days()
        if span > max_days:
            raise ValueError(f"date range ({span} days) exceeds the maximum of {max_days} days")
        return self


class BacktestRunOut(BaseModel):
    id: int
    idempotency_key: str
    status: str
    symbols: List[str]
    strategy: str
    data_provenance_mode: str
    start_date: date
    end_date: date
    evaluation_frequency_days: int
    holding_horizon_days: int
    target_price_horizon_days: int
    transaction_cost_bps: float
    slippage_bps: float
    confidence_threshold: Optional[float] = None
    recommendation_threshold: Optional[str] = None
    fundamental_reporting_lag_days: int
    calibration_version: Optional[str] = None
    progress_current: int
    progress_total: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    created_at: datetime


class BacktestStatusOut(BaseModel):
    id: int
    status: str
    progress_current: int
    progress_total: int
    cancel_requested: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class BacktestMetricsOut(BaseModel):
    id: int
    status: str
    data_provenance_mode: str
    symbols: List[str]
    metrics: Optional[Dict[str, Any]] = None


class RecommendationSnapshotOut(BaseModel):
    id: int
    symbol: str
    evaluated_at: datetime
    market_price_at_evaluation: Optional[float] = None
    recommendation: str
    total_score: float
    confidence_score: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    expected_return_pct: Optional[float] = None
    time_horizon: Optional[str] = None
    risk_level: Optional[str] = None
    position_size: Optional[str] = None
    price_bar_source: Optional[str] = None
    price_bar_is_synthetic: Optional[bool] = None
    engine_version: str
    calibration_version: Optional[str] = None


class BacktestTradesOut(BaseModel):
    id: int
    total: int
    limit: int
    offset: int
    trades: List[RecommendationSnapshotOut]


class ConfidenceCalibrationOut(BaseModel):
    id: int
    overall_error: Optional[float] = None
    buckets: List[Dict[str, Any]] = Field(default_factory=list)


class ComparisonEntryOut(BaseModel):
    run_id: int
    strategy: str
    status: str
    data_provenance_mode: str
    metrics: Optional[Dict[str, Any]] = None


class BacktestComparisonOut(BaseModel):
    id: int
    comparisons: List[ComparisonEntryOut]
    note: str


class CalibrationCreateRequest(BaseModel):
    config: Dict[str, Any]
    training_period_start: date
    training_period_end: date
    validation_period_start: date
    validation_period_end: date
    notes: Optional[str] = None
    random_seed: Optional[int] = None

    @model_validator(mode="after")
    def _validate_periods(self) -> "CalibrationCreateRequest":
        if self.training_period_end <= self.training_period_start:
            raise ValueError("training_period_end must be after training_period_start")
        if self.validation_period_end <= self.validation_period_start:
            raise ValueError("validation_period_end must be after validation_period_start")
        return self


class CalibrationConfigOut(BaseModel):
    version: str
    status: str
    config: Dict[str, Any]
    training_period_start: Optional[date] = None
    training_period_end: Optional[date] = None
    validation_period_start: Optional[date] = None
    validation_period_end: Optional[date] = None
    metrics: Optional[Dict[str, Any]] = None
    baseline_comparison_metrics: Optional[Dict[str, Any]] = None
    random_seed: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    activated_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None


class CalibrationListOut(BaseModel):
    calibrations: List[CalibrationConfigOut]


class CalibrationValidateRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1)
    data_provenance_mode: str = "SYNTHETIC"
    evaluation_frequency_days: int = Field(default=7, ge=1, le=365)
    holding_horizon_days: int = Field(default=20, ge=1, le=730)
    target_price_horizon_days: int = Field(default=60, ge=1, le=730)
    transaction_cost_bps: float = Field(default=0.0, ge=0, le=1000)
    slippage_bps: float = Field(default=0.0, ge=0, le=1000)
    confidence_threshold: Optional[float] = Field(default=None, ge=0, le=100)
    recommendation_threshold: Optional[str] = None
    fundamental_reporting_lag_days: int = Field(default=45, ge=0, le=365)

    @field_validator("symbols")
    @classmethod
    def _normalize_symbols(cls, value: List[str]) -> List[str]:
        deduped = list(dict.fromkeys(s.strip() for s in value if s.strip()))
        if not deduped:
            raise ValueError("symbols must contain at least one non-empty symbol")
        if len(deduped) > get_max_backtest_symbols():
            raise ValueError(f"symbols exceeds the maximum of {get_max_backtest_symbols()} per validation run")
        return deduped

    @field_validator("data_provenance_mode")
    @classmethod
    def _validate_provenance_mode(cls, value: str) -> str:
        if value not in _VALID_PROVENANCE_MODES:
            raise ValueError(f"data_provenance_mode must be one of {sorted(_VALID_PROVENANCE_MODES)}")
        return value
