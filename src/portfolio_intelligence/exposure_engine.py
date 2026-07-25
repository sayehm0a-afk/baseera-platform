"""ExposureEngine: dollar-weighted sector exposure analysis.

Deliberately distinct from `src.market_intelligence.sector_analysis.
SectorAnalyzer`: that engine averages per-symbol *scores* equally
across a market scan (every symbol counts once, regardless of size),
which is the right basis for "how is the Energy sector performing
market-wide." A portfolio's sector *exposure* is a different question
-- "how much of this portfolio's money sits in Energy" -- and must be
weighted by market value, not by symbol count. Reusing SectorAnalyzer
here would silently produce the wrong number (equal-weighted instead
of dollar-weighted), so this is a genuinely different calculation, not
a duplicate of Phase 7's sector logic.
"""

from typing import Dict, List

from src.portfolio_intelligence.types import HoldingAnalysis, SectorExposure

_UNCLASSIFIED_SECTOR = "Unclassified"


class ExposureEngine:
    def compute(self, holdings: List[HoldingAnalysis], total_value: float) -> List[SectorExposure]:
        by_sector: Dict[str, List[HoldingAnalysis]] = {}
        for holding in holdings:
            if holding.market_value is None:
                continue
            sector = holding.sector or _UNCLASSIFIED_SECTOR
            by_sector.setdefault(sector, []).append(holding)

        exposures = []
        for sector, sector_holdings in by_sector.items():
            market_value = sum(h.market_value for h in sector_holdings)
            exposures.append(
                SectorExposure(
                    sector=sector,
                    market_value=market_value,
                    weight=(market_value / total_value) if total_value > 0 else 0.0,
                    holdings_count=len(sector_holdings),
                    symbols=sorted(h.symbol for h in sector_holdings),
                )
            )

        exposures.sort(key=lambda e: e.weight, reverse=True)
        return exposures
