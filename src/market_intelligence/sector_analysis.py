"""SectorAnalyzer: groups one scan's `SymbolScanOutcome`s by
`Stock.sector` (already carried on each outcome by the scanner) and
computes per-sector aggregates. Averages/counts are computed only over
*successful* outcomes in a sector -- a skipped or failed symbol
contributes no data, honestly, rather than being silently treated as
neutral.

`momentum` needs a t-1 comparison, which is why
`SectorIntelligenceSummary` (unlike rankings/watchlists) is persisted
-- see that model's own docstring.
"""

from statistics import fmean
from typing import Dict, List, Optional, Tuple

from src.market_intelligence.types import SectorSummary, SymbolScanOutcome

_UNCLASSIFIED_SECTOR = "Unclassified"
_BUY_LIKE = {"BUY", "STRONG_BUY"}
_SELL_LIKE = {"SELL", "STRONG_SELL"}


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


def _mean_of(values: List[Optional[float]]) -> Optional[float]:
    present = [v for v in values if v is not None]
    return round(fmean(present), 4) if present else None


class SectorAnalyzer:
    def analyze(
        self,
        outcomes: List[SymbolScanOutcome],
        previous_summaries: Optional[Dict[str, float]] = None,
    ) -> List[SectorSummary]:
        """`previous_summaries` maps sector -> its previous
        `average_final_score`, the one value `momentum` is derived
        from; the caller (MarketIntelligenceEngine, via the
        repository) is responsible for loading it from the prior
        MarketScanRun's SectorIntelligenceSummary rows.
        """
        previous_summaries = previous_summaries or {}
        by_sector: Dict[str, List[SymbolScanOutcome]] = {}
        for outcome in outcomes:
            by_sector.setdefault(outcome.sector or _UNCLASSIFIED_SECTOR, []).append(outcome)

        summaries = []
        for sector, sector_outcomes in by_sector.items():
            successful = [o for o in sector_outcomes if _successful(o)]
            symbol_count = len(successful)

            buy_count = sum(1 for o in successful if o.recommendation and o.recommendation.value in _BUY_LIKE)
            sell_count = sum(1 for o in successful if o.recommendation and o.recommendation.value in _SELL_LIKE)
            hold_count = sum(1 for o in successful if o.recommendation and o.recommendation.value == "HOLD")

            average_final_score = _mean_of([o.final_score for o in successful])
            momentum = None
            if average_final_score is not None and sector in previous_summaries:
                momentum = round(average_final_score - previous_summaries[sector], 4)

            summaries.append(
                SectorSummary(
                    sector=sector,
                    symbol_count=symbol_count,
                    average_confidence=_mean_of([o.confidence for o in successful]),
                    average_final_score=average_final_score,
                    average_expected_return_pct=_mean_of([o.expected_return_pct for o in successful]),
                    average_technical_score=_mean_of([o.technical_score for o in successful]),
                    average_fundamental_score=_mean_of([o.fundamental_score for o in successful]),
                    buy_count=buy_count,
                    sell_count=sell_count,
                    hold_count=hold_count,
                    breadth=round(buy_count / symbol_count, 4) if symbol_count > 0 else 0.0,
                    momentum=momentum,
                )
            )
        return summaries

    @staticmethod
    def strongest_and_weakest(summaries: List[SectorSummary], top_n: int = 5) -> Tuple[List[str], List[str]]:
        ranked = sorted(
            (s for s in summaries if s.average_final_score is not None),
            key=lambda s: s.average_final_score, reverse=True,
        )
        strongest = [s.sector for s in ranked[:top_n]]
        weakest = [s.sector for s in ranked[-top_n:][::-1]] if ranked else []
        return strongest, weakest

    @staticmethod
    def rotation(summaries: List[SectorSummary], top_n: int = 5) -> Tuple[List[SectorSummary], List[SectorSummary]]:
        """Sectors rotating into favor (rising momentum) vs out of
        favor (falling momentum) -- empty on a scan with no prior
        scan to compare against (every `momentum` is `None` then)."""
        with_momentum = [s for s in summaries if s.momentum is not None]
        rotating_in = sorted(with_momentum, key=lambda s: s.momentum, reverse=True)[:top_n]
        rotating_out = sorted(with_momentum, key=lambda s: s.momentum)[:top_n]
        return rotating_in, rotating_out
