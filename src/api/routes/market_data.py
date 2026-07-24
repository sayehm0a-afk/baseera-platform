"""GET /api/v1/market-data/{symbol}/ohlcv

Uses the existing `load_price_bars` loader only (src/analysis/
ohlcv_loader.py) -- no new query logic against PriceBar, no
recomputation. Pagination (offset/page_size) is applied to the
already-loaded DataFrame here, in the route, not inside the loader --
the loader itself is untouched.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.analysis.composite.types import classify_freshness
from src.analysis.ohlcv_loader import load_price_bars
from src.api.dependencies import get_current_principal, get_db, get_stock_or_404
from src.api.middleware.request_id import get_request_id
from src.api.schemas.envelope import Envelope, ListEnvelope, Meta, PaginationMeta
from src.api.schemas.market_data import PriceBarSchema, ProviderHealthSchema
from src.domain.models import Stock, Timeframe
from src.market_data import config as market_data_config
from src.market_data.provider_factory import get_configured_provider

router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])

# NOTE (documented scope decision, see M2.12 completion report): this
# endpoint paginates by simple page/page_size over the already-loaded
# range, not a true opaque cursor -- a cursor keyed on `timestamp`
# (recommended in the pre-M2.12 API architecture review for exactly
# this endpoint) remains a reasonable future refinement, not built in
# this pass, to keep this milestone's scope bounded to what was asked.


@router.get("/provider/health", response_model=Envelope[ProviderHealthSchema])
async def get_provider_health(
    request: Request,
    principal: str = Depends(get_current_principal),
) -> Envelope[ProviderHealthSchema]:
    """Health of whichever provider MARKET_DATA_PROVIDER currently
    selects (M2.13 Objective 4's "Health monitoring" deliverable) --
    does not read or write price data, only calls the provider's own
    health_check()."""
    provider_name = market_data_config.get_configured_provider_name()
    provider = get_configured_provider()
    try:
        await provider.authenticate()
        status = await provider.health_check()
    finally:
        await provider.disconnect()

    now = datetime.now(timezone.utc)
    meta = Meta(
        as_of=now,
        freshness=classify_freshness(as_of=now, now=now).value,
        request_id=get_request_id(request),
    )
    data = ProviderHealthSchema(provider=provider_name, status=status.value)
    return Envelope(data=data, meta=meta)


@router.get("/{symbol}/ohlcv", response_model=ListEnvelope[PriceBarSchema])
def get_ohlcv(
    request: Request,
    stock: Stock = Depends(get_stock_or_404),
    db: Session = Depends(get_db),
    principal: str = Depends(get_current_principal),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
) -> ListEnvelope[PriceBarSchema]:
    price_df = load_price_bars(db, stock.id, Timeframe.ONE_DAY, start=start, end=end)
    total = len(price_df)
    offset = (page - 1) * page_size
    page_df = price_df.iloc[offset : offset + page_size]

    bars = [
        PriceBarSchema(
            timestamp=timestamp,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for timestamp, row in page_df.iterrows()
    ]

    now = datetime.now(timezone.utc)
    if total > 0:
        last_bar_at = price_df.index[-1]
        if last_bar_at.tzinfo is None:
            last_bar_at = last_bar_at.replace(tzinfo=timezone.utc)
        freshness = classify_freshness(as_of=last_bar_at, now=now).value
    else:
        freshness = "unknown"

    meta = Meta(as_of=now, freshness=freshness, request_id=get_request_id(request))
    pagination = PaginationMeta(page=page, page_size=page_size, total=total, has_next=offset + page_size < total)
    return ListEnvelope(data=bars, meta=meta, pagination=pagination)
