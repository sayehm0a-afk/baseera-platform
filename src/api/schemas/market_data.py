"""Response schema for /api/v1/market-data/{symbol}/ohlcv
(src/api/routes/market_data.py) -- wraps the existing PriceBar domain
model (src/domain/models/price_bar.py) field-for-field."""

from datetime import datetime

from pydantic import BaseModel


class PriceBarSchema(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    model_config = {"from_attributes": True}


class ProviderHealthSchema(BaseModel):
    """Response schema for GET /api/v1/market-data/provider/health
    (M2.13) -- wraps IMarketDataProvider.health_check()'s
    ProviderHealth enum for whichever provider MARKET_DATA_PROVIDER
    currently selects."""

    provider: str
    status: str
