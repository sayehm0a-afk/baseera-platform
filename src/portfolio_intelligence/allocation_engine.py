"""AllocationEngine: portfolio allocation analysis -- weight and market
value per holding plus cash, computed purely from already-analyzed
`HoldingAnalysis` objects. Computes no price, indicator, or ratio
itself; `HoldingAnalysis.latest_price`/`market_value` already came from
`PortfolioEngine`'s reuse of `AnalystEngine`/`build_analysis_context`.
"""

from datetime import datetime, timezone
from typing import List

from src.portfolio_intelligence.types import AllocationBreakdown, AllocationEntry, HoldingAnalysis


class AllocationEngine:
    def compute(self, holdings: List[HoldingAnalysis], cash: float) -> AllocationBreakdown:
        holdings_value = sum(h.market_value for h in holdings if h.market_value is not None)
        total_value = holdings_value + cash

        entries = [
            AllocationEntry(
                symbol=h.symbol,
                sector=h.sector,
                quantity=h.quantity,
                market_value=h.market_value,
                weight=(h.market_value / total_value) if h.market_value is not None and total_value > 0 else None,
            )
            for h in holdings
        ]

        return AllocationBreakdown(
            entries=entries,
            cash=cash,
            cash_weight=(cash / total_value) if total_value > 0 else 0.0,
            total_value=total_value,
            generated_at=datetime.now(timezone.utc),
        )
