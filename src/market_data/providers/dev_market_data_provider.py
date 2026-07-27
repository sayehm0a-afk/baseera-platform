"""Interim, non-production market data provider.

NOT REAL MARKET DATA. No licensed Tadawul (Saudi Exchange) data vendor
is contracted yet (see docs/architecture -- the approved M2 engineering
blueprint's risk assessment flags this as Critical and explicitly
authorizes a "clearly-labeled interim/mock-realistic provider" for M2.1
so downstream milestones aren't blocked on procurement). This provider
exists to satisfy that authorization: it implements IMarketDataProvider
with deterministic, synthetically-generated data -- no network calls,
safe to run in CI, fully reproducible -- so the ingestion pipeline and
domain models can be exercised end-to-end before a real vendor is
wired in.

Every value this class returns is synthetic. It must never be used, or
be mistaken for, real trading data.
"""

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from src.market_data.providers.market_data_provider import (
    IMarketDataProvider,
    MarketDataProviderFactory,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


def _seeded_value(seed_text: str, low: float, high: float) -> float:
    """Deterministic pseudo-random float in [low, high), seeded by seed_text."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF
    return low + fraction * (high - low)


class DevMarketDataProvider(IMarketDataProvider):
    """Deterministic synthetic-data provider for development and testing.

    NOT REAL MARKET DATA -- see module docstring.
    """

    def __init__(self, api_endpoint: str = "dev://synthetic", api_key: str = "dev"):
        # api_endpoint/api_key accepted only to satisfy MarketDataProviderFactory's
        # common construction signature; neither is used for any real call.
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self._connected = False

    async def authenticate(self) -> bool:
        self._connected = True
        logger.warning(
            "DevMarketDataProvider.authenticate(): no real authentication occurs -- "
            "this provider returns synthetic data only."
        )
        return True

    @staticmethod
    def _bar_for_day(symbol: str, day: date) -> Dict[str, Any]:
        """The single synthetic OHLCV bar for `symbol` on `day` --
        deterministic (same symbol+day always produces the same bar),
        shared by get_stock_data() (day=today) and
        get_historical_ohlcv() (one call per day in the range)."""
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_key = day.isoformat()
        base = _seeded_value(f"{symbol}:{day_key}", 10.0, 200.0)
        spread = base * 0.02
        open_price = round(base, 2)
        high_price = round(base + spread, 2)
        low_price = round(base - spread, 2)
        close_price = round(_seeded_value(f"{symbol}:{day_key}:close", low_price, high_price), 2)
        volume = int(_seeded_value(f"{symbol}:{day_key}:volume", 10_000, 5_000_000))
        return {
            "symbol": symbol,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
            # Anchored to the start of the day, not the call instant, so
            # repeated calls for the same symbol on the same day produce
            # the same bar identity (matches the OHLC values above, which
            # are already seeded by date, not by instant).
            "timestamp": day_start.isoformat(),
            "source": "dev-synthetic",
            "is_synthetic": True,
        }

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        return self._bar_for_day(symbol, today)

    async def get_historical_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> List[Dict[str, Any]]:
        """One synthetic bar per calendar day in [start, end] --
        deliberately does not skip weekends/holidays like a real
        Tadawul calendar would, the same simplification get_stock_data()
        already makes by always returning a bar regardless of what day
        it is. `interval` other than daily is not supported (no
        synthetic intraday model exists); anything else raises."""
        if interval != "1d":
            raise ValueError(
                f"DevMarketDataProvider.get_historical_ohlcv only supports interval='1d', got {interval!r}"
            )
        if start > end:
            return []
        bars = []
        day = start
        while day <= end:
            bars.append(self._bar_for_day(symbol, day))
            day += timedelta(days=1)
        return bars

    async def get_index_data(self, index_name: str) -> Dict[str, Any]:
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today = day_start.date().isoformat()
        value = round(_seeded_value(f"{index_name}:{today}", 8000.0, 13000.0), 2)
        change = round(_seeded_value(f"{index_name}:{today}:change", -100.0, 100.0), 2)
        change_percent = round((change / value) * 100, 4) if value else 0.0
        return {
            "index_name": index_name,
            "value": value,
            "change": change,
            "change_percent": change_percent,
            "timestamp": day_start.isoformat(),
            "source": "dev-synthetic",
            "is_synthetic": True,
        }

    async def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return [
            {
                "headline": f"[SYNTHETIC PLACEHOLDER {i + 1}] no real news source is connected yet",
                "timestamp": (now - timedelta(hours=i)).isoformat(),
                "source": "dev-synthetic",
                "is_synthetic": True,
            }
            for i in range(min(limit, 10))
        ]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY if self._connected else ProviderHealth.UNHEALTHY

    async def disconnect(self) -> None:
        self._connected = False


MarketDataProviderFactory.register("dev", DevMarketDataProvider)
