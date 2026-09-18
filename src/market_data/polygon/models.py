"""Typed, provider-agnostic shapes for parsed Polygon.io API responses.

PolygonClient returns raw dicts (the wire shape); PolygonMarketDataService
parses those dicts into the dataclasses below. Keeping the two separate
means a field-name change on Polygon's side is fixed in one place
(service.py's parsing), not scattered across every caller -- mirrors
src.market_data.sahmk.models's own separation exactly.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class PolygonBar:
    """One OHLCV aggregate bar from GET /v2/aggs/ticker/{ticker}/prev or
    GET /v2/aggs/ticker/{ticker}/range/.../.../.../.../....

    Field names mirror Polygon's own confirmed, documented aggregate-bar
    wire shape (`o`/`h`/`l`/`c`/`v`/`t`, optionally `vw`/`n`) -- `raw`
    always carries the untouched per-bar dict either way."""

    ticker: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    vwap: Optional[float]
    transactions: Optional[int]
    raw: dict


@dataclass(frozen=True)
class PolygonTickerDetails:
    """Reference metadata for one ticker, from GET
    /v3/reference/tickers/{ticker} (a single ticker's full detail) or one
    entry of GET /v3/reference/tickers (the bulk directory listing --
    `market_cap`/`description` are not present on that shape, so they
    are always None there; `raw` always carries the untouched response
    either way)."""

    ticker: str
    name: Optional[str]
    market: Optional[str]
    locale: Optional[str]
    primary_exchange: Optional[str]
    type: Optional[str]
    active: Optional[bool]
    currency_name: Optional[str]
    market_cap: Optional[float]
    description: Optional[str]
    raw: dict


@dataclass(frozen=True)
class PolygonNewsItem:
    """One news article from GET /v2/reference/news."""

    id: Optional[str]
    title: str
    tickers: List[str]
    published_utc: Optional[datetime]
    article_url: Optional[str]
    publisher_name: Optional[str]
    raw: dict


@dataclass(frozen=True)
class PolygonMarketStatus:
    """A market-status snapshot from GET /v1/marketstatus/now."""

    market: Optional[str]
    server_time: Optional[datetime]
    exchanges: dict
    raw: dict
