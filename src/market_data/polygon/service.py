"""Business-level service over PolygonClient.

Where PolygonClient returns raw response dicts, PolygonMarketDataService
validates required fields, parses them into the typed dataclasses in
models.py, and caches results (src.market_data.caching.ttl_cache.TTLCache
-- the same generic in-process cache class SahmkMarketDataService uses)
so repeated calls for the same ticker/window within a short window
don't re-hit a metered, rate-limited vendor -- especially significant
for Polygon's Free tier (5 requests/minute by default).

Cache TTLs: a previous close / market status change roughly once a
trading day / continuously, so they get a short-ish TTL; a past
trading day's aggregate bar never changes once the day has closed, so
historical bars get a long one -- mirrors sahmk/service.py's own TTL
reasoning.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.polygon.client import PolygonClient
from src.market_data.polygon.exceptions import PolygonResponseValidationError
from src.market_data.polygon.models import (
    PolygonBar,
    PolygonMarketStatus,
    PolygonNewsItem,
    PolygonTickerDetails,
)

logger = logging.getLogger(__name__)

PREVIOUS_CLOSE_CACHE_TTL_SECONDS = 15.0
AGGREGATES_CACHE_TTL_SECONDS = 3600.0
TICKER_DETAILS_CACHE_TTL_SECONDS = 86400.0  # a ticker's reference profile rarely changes
TICKER_DIRECTORY_CACHE_TTL_SECONDS = 86400.0  # the symbol universe rarely changes
NEWS_CACHE_TTL_SECONDS = 300.0
MARKET_STATUS_CACHE_TTL_SECONDS = 15.0


def _parse_timestamp_ms(value: Any) -> Optional[datetime]:
    """Polygon's confirmed, documented convention for aggregate-bar `t`
    fields: Unix milliseconds. Returns None (never guesses) if `value`
    isn't a real number."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        logger.warning("Could not parse Polygon millisecond timestamp %r; leaving unset.", value)
        return None


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.warning("Could not parse Polygon ISO timestamp %r; leaving unset.", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_fields(data: Dict[str, Any], fields: List[str], context: str) -> None:
    missing = [f for f in fields if f not in data or data[f] is None]
    if missing:
        raise PolygonResponseValidationError(
            f"Polygon {context} response is missing required field(s): {missing}", body=data
        )


def _bar_from_raw(ticker: str, bar: Dict[str, Any]) -> PolygonBar:
    """Parses one bar from Polygon's confirmed aggregate-bar wire shape
    (`o`/`h`/`l`/`c`/`v`/`t`, optionally `vw`/`n`) -- used by both
    get_previous_close and get_aggregates, which return bars in this
    same shape under `results`."""
    _require_fields(bar, ["o", "h", "l", "c", "v", "t"], "aggregate bar")
    return PolygonBar(
        ticker=ticker,
        open=float(bar["o"]),
        high=float(bar["h"]),
        low=float(bar["l"]),
        close=float(bar["c"]),
        volume=float(bar["v"]),
        timestamp=_parse_timestamp_ms(bar["t"]) or datetime.now(timezone.utc),
        vwap=_optional_float(bar.get("vw")),
        transactions=_optional_int(bar.get("n")),
        raw=bar,
    )


class PolygonMarketDataService:
    """Typed, cached, business-level access to Polygon.io US market data."""

    def __init__(self, client: Optional[PolygonClient] = None, cache: Optional[TTLCache] = None):
        self._client = client or PolygonClient()
        self._cache = cache if cache is not None else TTLCache()

    @property
    def has_credentials(self) -> bool:
        return self._client.has_credentials

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "PolygonMarketDataService":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ------------------------------------------------------------------

    async def get_previous_close(self, ticker: str) -> PolygonBar:
        async def _compute() -> PolygonBar:
            data = await self._client.get_previous_close(ticker)
            results = data.get("results") or []
            if not results:
                raise PolygonResponseValidationError(
                    f"Polygon returned no previous-close bar for '{ticker}'.", body=data
                )
            return _bar_from_raw(ticker, results[0])

        return await self._cache.get_or_compute(
            ("previous_close", ticker), _compute, ttl_seconds=PREVIOUS_CLOSE_CACHE_TTL_SECONDS, model=PolygonBar
        )

    async def get_aggregates(
        self,
        ticker: str,
        from_: date,
        to: date,
        multiplier: int = 1,
        timespan: str = "day",
        adjusted: bool = True,
    ) -> List[PolygonBar]:
        async def _compute() -> List[PolygonBar]:
            data = await self._client.get_aggregates(
                ticker, multiplier, timespan, from_, to, adjusted=adjusted
            )
            results = data.get("results") or []
            return [_bar_from_raw(ticker, bar) for bar in results]

        cache_key = ("aggregates", ticker, from_.isoformat(), to.isoformat(), multiplier, timespan)
        return await self._cache.get_or_compute(
            cache_key, _compute, ttl_seconds=AGGREGATES_CACHE_TTL_SECONDS, model=PolygonBar
        )

    async def get_daily_bar(self, ticker: str, on: Optional[date] = None) -> PolygonBar:
        """Most recent daily OHLCV bar for `ticker` as of `on` (default:
        today). Raises PolygonResponseValidationError if no bar is
        available for the requested day (e.g. a non-trading day)."""
        target_day = on or datetime.now(timezone.utc).date()
        bars = await self.get_aggregates(ticker, target_day, target_day, multiplier=1, timespan="day")
        if not bars:
            raise PolygonResponseValidationError(
                f"Polygon returned no daily bar for '{ticker}' on {target_day.isoformat()}."
            )
        return bars[-1]

    async def get_ticker_details(self, ticker: str) -> PolygonTickerDetails:
        async def _compute() -> PolygonTickerDetails:
            data = await self._client.get_ticker_details(ticker)
            result = data.get("results") or {}
            _require_fields(result, ["ticker"], "ticker details")
            return PolygonTickerDetails(
                ticker=result["ticker"],
                name=result.get("name"),
                market=result.get("market"),
                locale=result.get("locale"),
                primary_exchange=result.get("primary_exchange"),
                type=result.get("type"),
                active=result.get("active"),
                currency_name=result.get("currency_name"),
                market_cap=_optional_float(result.get("market_cap")),
                description=result.get("description"),
                raw=result,
            )

        return await self._cache.get_or_compute(
            ("ticker_details", ticker),
            _compute,
            ttl_seconds=TICKER_DETAILS_CACHE_TTL_SECONDS,
            model=PolygonTickerDetails,
        )

    async def get_ticker_directory(
        self, market: str = "stocks", active: bool = True
    ) -> List[PolygonTickerDetails]:
        """The Polygon US ticker directory from GET /v3/reference/tickers
        (PolygonClient.get_tickers() already follows the endpoint's own
        `next_url` pagination -- see that method's docstring). Entries
        from this bulk listing carry no `market_cap`/`description`
        (only GET /v3/reference/tickers/{ticker} returns those) -- both
        are left None rather than guessed at."""

        async def _compute() -> List[PolygonTickerDetails]:
            data = await self._client.get_tickers(market=market, active=active)
            results = data.get("results") or []
            return [
                PolygonTickerDetails(
                    ticker=item["ticker"],
                    name=item.get("name"),
                    market=item.get("market"),
                    locale=item.get("locale"),
                    primary_exchange=item.get("primary_exchange"),
                    type=item.get("type"),
                    active=item.get("active"),
                    currency_name=item.get("currency_name"),
                    market_cap=None,
                    description=None,
                    raw=item,
                )
                for item in results
                if item.get("ticker")
            ]

        return await self._cache.get_or_compute(
            ("ticker_directory", market, active),
            _compute,
            ttl_seconds=TICKER_DIRECTORY_CACHE_TTL_SECONDS,
            model=PolygonTickerDetails,
        )

    async def get_ticker_news(self, ticker: Optional[str] = None, limit: int = 10) -> List[PolygonNewsItem]:
        async def _compute() -> List[PolygonNewsItem]:
            data = await self._client.get_ticker_news(ticker=ticker, limit=limit)
            results = data.get("results") or []
            return [
                PolygonNewsItem(
                    id=item.get("id"),
                    title=item.get("title") or "",
                    tickers=item.get("tickers") or [],
                    published_utc=_parse_iso_timestamp(item.get("published_utc")),
                    article_url=item.get("article_url"),
                    publisher_name=(item.get("publisher") or {}).get("name"),
                    raw=item,
                )
                for item in results
            ]

        return await self._cache.get_or_compute(
            ("news", ticker, limit), _compute, ttl_seconds=NEWS_CACHE_TTL_SECONDS, model=PolygonNewsItem
        )

    async def get_market_status(self) -> PolygonMarketStatus:
        async def _compute() -> PolygonMarketStatus:
            data = await self._client.get_market_status()
            return PolygonMarketStatus(
                market=data.get("market"),
                server_time=_parse_iso_timestamp(data.get("serverTime")),
                exchanges=data.get("exchanges") or {},
                raw=data,
            )

        return await self._cache.get_or_compute(
            "market_status", _compute, ttl_seconds=MARKET_STATUS_CACHE_TTL_SECONDS, model=PolygonMarketStatus
        )

    async def check_health(self) -> bool:
        """Cheapest confirmed call (GET /v1/marketstatus/now) used to
        verify the configured key is accepted and the host is
        reachable. Returns False for any failure rather than raising --
        callers that need the specific failure reason should call
        get_market_status() directly instead."""
        try:
            await self.get_market_status()
            return True
        except Exception as exc:  # noqa: BLE001 -- deliberate: this is a boolean health probe
            logger.info("Polygon health check failed: %s", exc)
            return False


def _optional_float(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def _optional_int(value: Any) -> Optional[int]:
    return int(value) if value is not None else None
