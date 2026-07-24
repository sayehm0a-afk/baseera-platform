"""Interim, non-production fundamental data provider.

NOT REAL FINANCIAL DATA. No licensed fundamentals vendor is contracted
(same "no data vendor" gap as DevMarketDataProvider/M2.1, unchanged by
this milestone). This provider exists so the fundamental analysis
layer can be exercised end-to-end before a real vendor is wired in: it
implements IFundamentalDataProvider with deterministic, synthetically
generated financial-statement figures -- no network calls, safe to run
in CI, fully reproducible.

Deliberately self-contained: does not import from
dev_market_data_provider.py, even though both use the same seeded-hash
technique, to avoid coupling two otherwise-independent Dev providers
together over an implementation detail neither's public contract
depends on.

Every value this class returns is synthetic. It must never be used, or
be mistaken for, real reported financial data.
"""

import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict

from src.market_data.providers.fundamental_data_provider import (
    FundamentalDataProviderFactory,
    IFundamentalDataProvider,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


def _seeded_value(seed_text: str, low: float, high: float) -> float:
    """Deterministic pseudo-random float in [low, high), seeded by seed_text."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF
    return low + fraction * (high - low)


def _most_recent_period_end(period_type: str, today: date) -> date:
    """The most recently *completed* fiscal period end on or before
    today, for the given period type."""
    if period_type == "annual":
        return date(today.year - 1, 12, 31)
    if period_type == "quarterly":
        quarter_ends = [date(today.year, month, day) for month, day in ((3, 31), (6, 30), (9, 30), (12, 31))]
        completed = [d for d in quarter_ends if d < today]
        return max(completed) if completed else date(today.year - 1, 12, 31)
    raise ValueError(f"Unsupported period_type: {period_type!r}")


class DevFundamentalDataProvider(IFundamentalDataProvider):
    """Deterministic synthetic-data provider for development and testing.

    NOT REAL FINANCIAL DATA -- see module docstring.
    """

    def __init__(self):
        self._connected = False

    async def authenticate(self) -> bool:
        self._connected = True
        logger.warning(
            "DevFundamentalDataProvider.authenticate(): no real authentication occurs -- "
            "this provider returns synthetic data only."
        )
        return True

    async def get_fundamentals(self, symbol: str, period_type: str = "annual") -> Dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        fiscal_period_end = _most_recent_period_end(period_type, today)
        key = f"{symbol}:{period_type}:{fiscal_period_end.isoformat()}"

        revenue = _seeded_value(f"{key}:revenue", 1_000_000_000, 50_000_000_000)
        if period_type == "quarterly":
            # A quarter is roughly a quarter of annual revenue -- a
            # deliberate, documented simplification, not a claim about
            # real seasonality.
            revenue = revenue / 4
        revenue = round(revenue, 2)

        gross_profit = round(revenue * _seeded_value(f"{key}:gross_margin", 0.15, 0.55), 2)
        net_income = round(revenue * _seeded_value(f"{key}:net_margin", 0.03, 0.30), 2)
        total_assets = round(_seeded_value(f"{key}:total_assets", revenue * 1.5, revenue * 6.0), 2)
        total_equity = round(total_assets * _seeded_value(f"{key}:equity_ratio", 0.35, 0.75), 2)
        total_liabilities = round(total_assets - total_equity, 2)
        current_assets = round(total_assets * _seeded_value(f"{key}:current_asset_ratio", 0.15, 0.45), 2)
        current_liabilities = round(
            current_assets * _seeded_value(f"{key}:current_liability_ratio", 0.4, 0.9), 2
        )
        inventory = round(current_assets * _seeded_value(f"{key}:inventory_ratio", 0.05, 0.3), 2)
        cash_and_equivalents = round(current_assets * _seeded_value(f"{key}:cash_ratio", 0.1, 0.4), 2)
        total_debt = round(total_liabilities * _seeded_value(f"{key}:debt_ratio", 0.2, 0.6), 2)
        shares_outstanding = int(_seeded_value(f"{key}:shares", 100_000_000, 10_000_000_000))
        eps = round(net_income / shares_outstanding, 4) if shares_outstanding else 0.0
        dividend_per_share = round(eps * _seeded_value(f"{key}:payout_ratio", 0.0, 0.6), 4)

        return {
            "symbol": symbol,
            "period_type": period_type,
            "fiscal_period_end": fiscal_period_end.isoformat(),
            "revenue": revenue,
            "gross_profit": gross_profit,
            "net_income": net_income,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "inventory": inventory,
            "cash_and_equivalents": cash_and_equivalents,
            "total_debt": total_debt,
            "shares_outstanding": shares_outstanding,
            "eps": eps,
            "dividend_per_share": dividend_per_share,
            "source": "dev-synthetic",
            "is_synthetic": True,
        }

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY if self._connected else ProviderHealth.UNHEALTHY

    async def disconnect(self) -> None:
        self._connected = False


FundamentalDataProviderFactory.register("dev", DevFundamentalDataProvider)
