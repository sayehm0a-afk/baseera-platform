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
from datetime import datetime, timedelta, timezone
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

    async def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today = day_start.date().isoformat()
        base = _seeded_value(f"{symbol}:{today}", 10.0, 200.0)
        spread = base * 0.02
        open_price = round(base, 2)
        high_price = round(base + spread, 2)
        low_price = round(base - spread, 2)
        close_price = round(_seeded_value(f"{symbol}:{today}:close", low_price, high_price), 2)
        volume = int(_seeded_value(f"{symbol}:{today}:volume", 10_000, 5_000_000))
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
