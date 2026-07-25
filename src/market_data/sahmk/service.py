"""Business-level service over SahmkClient.

Where SahmkClient returns raw response dicts, SahmkMarketDataService
validates required fields, parses them into the typed dataclasses in
models.py, and caches results (src.market_data.caching.TTLCache) so
repeated calls for the same symbol/index within a short window don't
re-hit a metered, rate-limited vendor.

Cache TTLs: quotes and index snapshots change continuously during
trading hours, so they get a short TTL; a past trading day's bar never
changes once the day has closed, so historical bars get a long one.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.sahmk.client import SahmkClient
from src.market_data.sahmk.exceptions import SahmkResponseValidationError
from src.market_data.sahmk.models import (
    SahmkEvent,
    SahmkHistoricalBar,
    SahmkMarketSummary,
    SahmkQuote,
)

logger = logging.getLogger(__name__)

QUOTE_CACHE_TTL_SECONDS = 15.0
MARKET_SUMMARY_CACHE_TTL_SECONDS = 15.0
HISTORICAL_CACHE_TTL_SECONDS = 3600.0
EVENTS_CACHE_TTL_SECONDS = 300.0


def _parse_timestamp(value: Any) -> Optional[datetime]:
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
        logger.warning("Could not parse SAHMK timestamp %r; leaving unset.", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_fields(data: Dict[str, Any], fields: List[str], context: str) -> None:
    missing = [f for f in fields if f not in data or data[f] is None]
    if missing:
        raise SahmkResponseValidationError(
            f"SAHMK {context} response is missing required field(s): {missing}", body=data
        )


class SahmkMarketDataService:
    """Typed, cached, business-level access to SAHMK market data."""

    def __init__(self, client: Optional[SahmkClient] = None, cache: Optional[TTLCache] = None):
        self._client = client or SahmkClient()
        self._cache = cache if cache is not None else TTLCache()

    @property
    def has_credentials(self) -> bool:
        return self._client.has_credentials

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "SahmkMarketDataService":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ------------------------------------------------------------------

    async def get_latest_quote(self, symbol: str) -> SahmkQuote:
        async def _compute() -> SahmkQuote:
            data = await self._client.get_quote(symbol)
            _require_fields(data, ["price"], "quote")
            return SahmkQuote(
                symbol=symbol,
                price=float(data["price"]),
                change=_optional_float(data.get("change")),
                change_percent=_optional_float(data.get("change_percent")),
                volume=_optional_int(data.get("volume")),
                timestamp=_parse_timestamp(data.get("timestamp")) or datetime.now(timezone.utc),
            )

        return await self._cache.get_or_compute(
            ("quote", symbol), _compute, ttl_seconds=QUOTE_CACHE_TTL_SECONDS
        )

    async def get_historical_bars(
        self,
        symbol: str,
        date_from: date,
        date_to: date,
        interval: str = "1d",
    ) -> List[SahmkHistoricalBar]:
        async def _compute() -> List[SahmkHistoricalBar]:
            data = await self._client.get_historical(
                symbol, interval=interval, date_from=date_from, date_to=date_to
            )
            bars = data.get("bars", [])
            result: List[SahmkHistoricalBar] = []
            for bar in bars:
                _require_fields(
                    bar, ["open", "high", "low", "close", "volume", "timestamp"], "historical bar"
                )
                result.append(
                    SahmkHistoricalBar(
                        symbol=symbol,
                        open=float(bar["open"]),
                        high=float(bar["high"]),
                        low=float(bar["low"]),
                        close=float(bar["close"]),
                        volume=int(bar["volume"]),
                        timestamp=_parse_timestamp(bar["timestamp"]),
                    )
                )
            return result

        cache_key = ("historical", symbol, date_from.isoformat(), date_to.isoformat(), interval)
        return await self._cache.get_or_compute(
            cache_key, _compute, ttl_seconds=HISTORICAL_CACHE_TTL_SECONDS
        )

    async def get_daily_bar(self, symbol: str, on: Optional[date] = None) -> SahmkHistoricalBar:
        """Most recent daily OHLCV bar for `symbol` as of `on` (default:
        today). Raises SahmkResponseValidationError if no bar is
        available for the requested day (e.g. a non-trading day)."""
        target_day = on or datetime.now(timezone.utc).date()
        bars = await self.get_historical_bars(symbol, target_day, target_day, interval="1d")
        if not bars:
            raise SahmkResponseValidationError(
                f"SAHMK returned no historical bar for '{symbol}' on {target_day.isoformat()}."
            )
        return bars[-1]

    async def get_index_snapshot(self, index: str = "TASI") -> SahmkMarketSummary:
        async def _compute() -> SahmkMarketSummary:
            data = await self._client.get_market_summary(index=index)
            _require_fields(data, ["index_value"], "market summary")
            return SahmkMarketSummary(
                index=index,
                value=float(data["index_value"]),
                change=_optional_float(data.get("index_change")),
                change_percent=_optional_float(data.get("index_change_percent")),
                timestamp=_parse_timestamp(data.get("timestamp")),
            )

        return await self._cache.get_or_compute(
            ("summary", index), _compute, ttl_seconds=MARKET_SUMMARY_CACHE_TTL_SECONDS
        )

    async def get_recent_events(self, limit: int = 10) -> List[SahmkEvent]:
        async def _compute() -> List[SahmkEvent]:
            data = await self._client.get_events(limit=limit)
            items = data.get("events", data.get("results", []))
            return [
                SahmkEvent(
                    symbol=item.get("symbol"),
                    headline=item.get("headline") or item.get("title") or "",
                    timestamp=_parse_timestamp(item.get("timestamp")),
                    raw=item,
                )
                for item in items
            ]

        return await self._cache.get_or_compute(
            ("events", limit), _compute, ttl_seconds=EVENTS_CACHE_TTL_SECONDS
        )

    async def check_health(self) -> bool:
        """Cheapest confirmed call (GET /market/summary/) used to verify
        the configured key is accepted and the host is reachable.
        Returns False for any failure rather than raising -- callers
        that need the specific failure reason should call
        get_index_snapshot() directly instead."""
        try:
            await self.get_index_snapshot("TASI")
            return True
        except Exception as exc:  # noqa: BLE001 -- deliberate: this is a boolean health probe
            logger.info("SAHMK health check failed: %s", exc)
            return False


def _optional_float(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def _optional_int(value: Any) -> Optional[int]:
    return int(value) if value is not None else None
