"""MarketSnapshotBuilder: assembles the market-wide sentiment summary
(`MarketSnapshotData`) from one scan's outcomes, sector summaries, and
change events -- reuses `SectorAnalyzer.strongest_and_weakest()` for
the sector ranking rather than re-deriving it, and reads change events
`ChangeDetector` already produced rather than recomputing any delta.
"""

from datetime import datetime, timezone
from statistics import fmean
from typing import List, Optional

from src.market_intelligence.config import get_snapshot_top_changes_count, get_snapshot_top_sectors_count
from src.market_intelligence.ordinals import RECOMMENDATION_RANK
from src.market_intelligence.sector_analysis import SectorAnalyzer
from src.market_intelligence.types import ChangeDetectionResult, MarketSnapshotData, SectorSummary, SymbolScanOutcome

_BUY_LIKE = {"BUY", "STRONG_BUY"}
_SELL_LIKE = {"SELL", "STRONG_SELL"}
_CENTER = 2  # RECOMMENDATION_RANK runs 0..4 (STRONG_SELL..STRONG_BUY); centered on HOLD=2 -> -2..+2


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


class MarketSnapshotBuilder:
    def build(
        self,
        outcomes: List[SymbolScanOutcome],
        sector_summaries: List[SectorSummary],
        change_result: Optional[ChangeDetectionResult] = None,
    ) -> MarketSnapshotData:
        successful = [o for o in outcomes if _successful(o)]
        generated_at = datetime.now(timezone.utc)

        buy_count = sum(1 for o in successful if o.recommendation and o.recommendation.value in _BUY_LIKE)
        sell_count = sum(1 for o in successful if o.recommendation and o.recommendation.value in _SELL_LIKE)

        confidences = [o.confidence for o in successful if o.confidence is not None]
        recommendation_scores = [
            RECOMMENDATION_RANK[o.recommendation] - _CENTER for o in successful if o.recommendation is not None
        ]

        strongest_sectors, weakest_sectors = SectorAnalyzer.strongest_and_weakest(
            sector_summaries, top_n=get_snapshot_top_sectors_count()
        )

        most_important_changes = []
        if change_result is not None:
            with_delta = [e for e in change_result.events if e.delta is not None]
            most_important_changes = sorted(with_delta, key=lambda e: abs(e.delta), reverse=True)[
                : get_snapshot_top_changes_count()
            ]

        return MarketSnapshotData(
            generated_at=generated_at,
            symbols_scanned=len(successful),
            bull_bear_ratio=round(buy_count / sell_count, 4) if sell_count > 0 else None,
            average_confidence=round(fmean(confidences), 4) if confidences else None,
            average_recommendation_score=round(fmean(recommendation_scores), 4) if recommendation_scores else None,
            buy_signal_count=buy_count,
            sell_signal_count=sell_count,
            strongest_sectors=strongest_sectors,
            weakest_sectors=weakest_sectors,
            most_important_changes=most_important_changes,
        )
