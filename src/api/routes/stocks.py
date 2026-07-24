"""GET /api/v1/stocks, GET /api/v1/stocks/{symbol}

Plain reference-data lookups against the existing Stock domain model
(src/domain/models/stock.py) -- no analysis engine involved. Left
unauthenticated, unlike /analysis/* and /market-data/* (which require
get_current_principal): company symbol/name/sector reference data is
not the platform's proprietary computed output, matching how public
stock-exchange listings are ordinarily open lookup data. Documented
here as a deliberate, disclosed choice, not an oversight -- see the
M2.12 completion report for the full rationale.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_stock_or_404
from src.api.middleware.request_id import get_request_id
from src.api.schemas.envelope import Envelope, ListEnvelope, Meta, PaginationMeta
from src.api.schemas.stocks import StockDetail, StockSummary
from src.domain.models import Stock

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


def _meta(request: Request) -> Meta:
    now = datetime.now(timezone.utc)
    return Meta(as_of=now, freshness="fresh", request_id=get_request_id(request))


@router.get("", response_model=ListEnvelope[StockSummary])
def list_stocks(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ListEnvelope[StockSummary]:
    query = db.query(Stock).order_by(Stock.symbol.asc())
    total = query.count()
    offset = (page - 1) * page_size
    stocks = query.offset(offset).limit(page_size).all()
    data = [StockSummary.model_validate(stock) for stock in stocks]
    pagination = PaginationMeta(page=page, page_size=page_size, total=total, has_next=offset + page_size < total)
    return ListEnvelope(data=data, meta=_meta(request), pagination=pagination)


@router.get("/{symbol}", response_model=Envelope[StockDetail])
def get_stock(request: Request, stock: Stock = Depends(get_stock_or_404)) -> Envelope[StockDetail]:
    data = StockDetail.model_validate(stock)
    return Envelope(data=data, meta=_meta(request))
