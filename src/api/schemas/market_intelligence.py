"""Request/response schemas for /api/v1/market/* -- follows the same
conventions as src/api/schemas/backtesting.py and stocks.py.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MarketScanRequest(BaseModel):
    symbols: Optional[List[str]] = Field(
        default=None,
        description="Explicit symbols to scan; omit to scan every active, price-history-eligible symbol.",
    )


class MarketScanRunOut(BaseModel):
    id: int
    status: str
    symbols_requested: int
    symbols_succeeded: int
    symbols_skipped: int
    symbols_failed: int
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    created_at: datetime


class MarketScanProgressOut(BaseModel):
    """Live progress for one MarketScanRun, read from MarketScanProgress
    (src.market_intelligence.scan_progress.ScanProgressTracker writes
    this row after every symbol). Returns 404 (via NoMarketScanDataError)
    if no progress row exists yet for the run -- e.g. a run dispatched
    by a code path that doesn't use a ScanProgressTracker."""

    run_id: int
    status: str
    eligible_discovered: int
    completed_count: int
    remaining_count: int
    progress_pct: float
    success_count: int
    failed_count: int
    skipped_count: int
    insufficient_data_count: int
    published_count: int
    rejected_count: int
    watch_only_count: int
    not_evaluated_count: int
    current_symbol: Optional[str] = None
    current_symbol_name_en: Optional[str] = None
    current_symbol_name_ar: Optional[str] = None
    last_completed_symbol: Optional[str] = None
    api_calls_total: int
    retries_total: int
    latest_error: Optional[str] = None
    latest_warning: Optional[str] = None
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RankingEntryOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    final_score: Optional[float] = None
    target_price: Optional[float] = None
    expected_return_pct: Optional[float] = None
    risk_level: Optional[str] = None
    rank_value: Optional[float] = None


class RankingListOut(BaseModel):
    category: str
    entries: List[RankingEntryOut]
    generated_at: datetime


class RankingsOut(BaseModel):
    scan_run_id: Optional[int] = None
    rankings: List[RankingListOut]


class WatchlistEntryOut(BaseModel):
    symbol: str
    sector: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    reason: str


class WatchlistResultOut(BaseModel):
    category: str
    entries: List[WatchlistEntryOut]
    generated_at: datetime


class WatchlistsOut(BaseModel):
    scan_run_id: Optional[int] = None
    watchlists: List[WatchlistResultOut]


class SectorSummaryOut(BaseModel):
    sector: str
    symbol_count: int
    average_confidence: Optional[float] = None
    average_final_score: Optional[float] = None
    average_expected_return_pct: Optional[float] = None
    average_technical_score: Optional[float] = None
    average_fundamental_score: Optional[float] = None
    buy_count: int
    sell_count: int
    hold_count: int
    breadth: float
    momentum: Optional[float] = None


class SectorsOut(BaseModel):
    scan_run_id: Optional[int] = None
    sectors: List[SectorSummaryOut]


class ChangeEventOut(BaseModel):
    symbol: str
    change_type: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    delta: Optional[float] = None
    detected_at: datetime


class ChangesOut(BaseModel):
    total: int
    limit: int
    offset: int
    changes: List[ChangeEventOut]


class AlertOut(BaseModel):
    alert_type: str
    severity: str
    symbol: Optional[str] = None
    sector: Optional[str] = None
    message: str
    generated_at: datetime


class AlertsOut(BaseModel):
    total: int
    limit: int
    offset: int
    alerts: List[AlertOut]


class DiagnosticSampleSymbolOut(BaseModel):
    symbol: str
    recommendation: str
    latest_price: Optional[float] = None
    evaluated_at: datetime


class DiagnosticScanOut(BaseModel):
    """Response for POST /api/v1/admin/market-intelligence/diagnostic-scan
    -- real evidence from one controlled SAHMK poll, never fabricated:
    every field below is either read from provider_factory's real
    connectivity-probe state or from rows the scan itself just wrote."""

    triggered_at: datetime
    operation_tested: str
    sahmk_connectivity_status: str
    sahmk_error: Optional[str] = None
    current_provider_kind: Optional[str] = None
    last_connectivity_status: Optional[str] = None
    last_connectivity_at: Optional[str] = None
    can_publish_recommendations: bool
    strict_real_data: bool
    synthetic_allowed: bool
    sahmk_key_present: bool
    run_id: Optional[int] = None
    run_status: Optional[str] = None
    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    rows_written: int = 0
    sample_symbols: List[DiagnosticSampleSymbolOut] = Field(default_factory=list)
    last_scan_source: Optional[str] = None
    data_is_fresh: Optional[bool] = None
    freshness_note: str = ""


class MarketSummaryOut(BaseModel):
    scan_run_id: Optional[int] = None
    generated_at: datetime
    symbols_scanned: int
    bull_bear_ratio: Optional[float] = None
    average_confidence: Optional[float] = None
    average_recommendation_score: Optional[float] = None
    buy_signal_count: int
    sell_signal_count: int
    strongest_sectors: List[str]
    weakest_sectors: List[str]
    most_important_changes: List[ChangeEventOut]
