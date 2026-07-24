"""Response schemas for /api/v1/stocks (src/api/routes/stocks.py) --
wraps the existing Stock domain model (src/domain/models/stock.py)
field-for-field, no new fields invented."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class StockSummary(BaseModel):
    symbol: str
    name_en: str
    name_ar: Optional[str]
    sector: Optional[str]
    currency: str
    is_active: bool

    model_config = {"from_attributes": True}


class StockDetail(StockSummary):
    lot_size: int
    listed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
