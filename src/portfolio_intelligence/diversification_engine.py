"""DiversificationEngine: Herfindahl-Hirschman-Index-based
concentration risk and a diversification score.

The Herfindahl-Hirschman Index (HHI) is a standard concentration
measure (sum of squared weights, 0 = infinitely diversified, 1 = a
single position); its complement `1 - HHI` is the standard
"diversification index." No proprietary or fabricated formula --
these are the textbook definitions, computed purely from `weight`
fields `AllocationEngine`/`ExposureEngine` already produced.
"""

from typing import List, Tuple

from src.portfolio_intelligence.config import get_position_concentration_threshold
from src.portfolio_intelligence.types import ConcentrationRisk, DiversificationScore, HoldingAnalysis, SectorExposure

_POSITION_WEIGHT = 0.6
_SECTOR_WEIGHT = 0.4


def _herfindahl_index(weights: List[float]) -> float:
    return sum(w * w for w in weights)


class DiversificationEngine:
    def compute(
        self, holdings: List[HoldingAnalysis], sector_exposure: List[SectorExposure]
    ) -> Tuple[DiversificationScore, ConcentrationRisk]:
        position_weights = [h.weight for h in holdings if h.weight is not None]
        sector_weights = [s.weight for s in sector_exposure]

        position_hhi = _herfindahl_index(position_weights)
        sector_hhi = _herfindahl_index(sector_weights)

        concentration = self._concentration_risk(holdings, position_weights, position_hhi, sector_hhi)
        diversification = self._diversification_score(
            position_weights, sector_weights, position_hhi, sector_hhi, len(holdings), len(sector_exposure)
        )
        return diversification, concentration

    @staticmethod
    def _concentration_risk(
        holdings: List[HoldingAnalysis], position_weights: List[float], position_hhi: float, sector_hhi: float
    ) -> ConcentrationRisk:
        threshold = get_position_concentration_threshold()
        ranked = sorted((h for h in holdings if h.weight is not None), key=lambda h: h.weight, reverse=True)

        largest_symbol = ranked[0].symbol if ranked else None
        largest_weight = ranked[0].weight if ranked else None
        top_3_weight = sum(h.weight for h in ranked[:3])

        return ConcentrationRisk(
            herfindahl_index=round(position_hhi, 6),
            sector_herfindahl_index=round(sector_hhi, 6),
            largest_position_symbol=largest_symbol,
            largest_position_weight=largest_weight,
            top_3_weight=round(top_3_weight, 6),
            is_concentrated=bool(largest_weight is not None and largest_weight >= threshold),
            concentration_threshold=threshold,
        )

    @staticmethod
    def _diversification_score(
        position_weights: List[float],
        sector_weights: List[float],
        position_hhi: float,
        sector_hhi: float,
        holdings_count: int,
        sector_count: int,
    ) -> DiversificationScore:
        if not position_weights:
            return DiversificationScore(
                score=0.0, effective_number_of_holdings=0.0, effective_number_of_sectors=0.0,
                sector_count=sector_count, holdings_count=holdings_count,
                narrative="No holdings with a computable weight -- diversification cannot be assessed.",
            )

        position_diversification_index = 1.0 - position_hhi
        sector_diversification_index = 1.0 - sector_hhi if sector_weights else 0.0
        score = round((_POSITION_WEIGHT * position_diversification_index + _SECTOR_WEIGHT * sector_diversification_index) * 100.0, 2)

        effective_holdings = round(1.0 / position_hhi, 2) if position_hhi > 0 else 0.0
        effective_sectors = round(1.0 / sector_hhi, 2) if sector_hhi > 0 else 0.0

        narrative = (
            f"{holdings_count} holding(s) across {sector_count} sector(s); effective number of holdings "
            f"(1/HHI) is {effective_holdings:.1f}, effective number of sectors is {effective_sectors:.1f}."
        )

        return DiversificationScore(
            score=score, effective_number_of_holdings=effective_holdings, effective_number_of_sectors=effective_sectors,
            sector_count=sector_count, holdings_count=holdings_count, narrative=narrative,
        )
