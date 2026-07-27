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
