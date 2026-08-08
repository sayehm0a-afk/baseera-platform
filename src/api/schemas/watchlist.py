"""GET/POST/DELETE /api/v1/watchlist -- the authenticated user's own
personal watchlist (distinct from GET /api/v1/market/watchlists, which
returns scan-derived category lists like TOP_BUY, not a user's saved
symbols).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WatchlistItemOut(BaseModel):
    """One saved symbol plus the most recent Decision Engine V2
    snapshot already persisted for it, if any -- never recomputed on
    read. `latest_decision_*` fields are all null when no snapshot has
    been produced for this symbol yet (a real "not yet analyzed"
    state, not a fabricated one)."""

    symbol: str
    added_at: datetime

    company_name_ar: Optional[str] = None
    sector_ar: Optional[str] = None

    latest_decision: Optional[str] = None
    latest_decision_label_ar: Optional[str] = None
    latest_confidence_score: Optional[float] = None
    latest_current_price: Optional[float] = None
    latest_entry_zone_low: Optional[float] = None
    latest_entry_zone_high: Optional[float] = None
    latest_target_1: Optional[float] = None
    latest_target_2: Optional[float] = None
    latest_target_3: Optional[float] = None
    latest_stop_loss: Optional[float] = None
    latest_data_freshness_status: Optional[str] = None
    latest_decision_timestamp: Optional[datetime] = None


class WatchlistOut(BaseModel):
    generated_at: datetime
    items: List[WatchlistItemOut] = Field(default_factory=list)


class AddWatchlistItemRequest(BaseModel):
    symbol: str
