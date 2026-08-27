"""RebalanceEngine: assembles the full rebalance plan -- one action per
existing holding (via `PositionSizer`, reused unmodified) plus a list
of new-buy opportunities for symbols not currently held.

New-buy opportunities reuse Phase 7's `src.market_intelligence`
machinery directly: if a completed `MarketScanRun` exists, its
persisted `SymbolIntelligenceRecord`s are reconstructed into
`SymbolScanOutcome`s (via `read_model.outcome_from_record`, exactly as
the market REST routes already do) and handed to the same
`RankingEngine` that powers `GET /api/v1/market/top-buy` -- this
package never re-implements "what counts as a buy opportunity." When
no market scan has ever run, the list is honestly empty with a
disclosed reason, never fabricated.
"""

from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from src.market_intelligence.ranking import RankingEngine
from src.market_intelligence.read_model import outcome_from_record
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.types import RankingCategory
from src.portfolio_intelligence.config import get_max_new_buy_opportunities
from src.portfolio_intelligence.position_sizer import PositionSizer
from src.portfolio_intelligence.types import (
    HoldingAnalysis,
    NewBuyOpportunity,
    PortfolioRiskProfile,
    RebalancePlan,
    SectorExposure,
)

_NO_SCAN_SOURCE = "No completed market scan exists yet -- POST /api/v1/market/scan to enable new-buy-opportunity suggestions."


class RebalanceEngine:
    def __init__(
        self,
        session: Session,
        market_intelligence_repository: MarketIntelligenceRepository = None,
        position_sizer: PositionSizer = None,
        ranking_engine: RankingEngine = None,
    ):
        self._session = session
        self._repository = market_intelligence_repository or MarketIntelligenceRepository()
        self._position_sizer = position_sizer or PositionSizer()
        self._ranking_engine = ranking_engine or RankingEngine()

    def plan(
        self,
        holdings: List[HoldingAnalysis],
        risk_profile: PortfolioRiskProfile,
        sector_exposure: List[SectorExposure],
    ) -> RebalancePlan:
        actions = [self._position_sizer.size(h) for h in holdings if h.available]
        new_buy_opportunities, source = self._find_new_buy_opportunities(holdings)

        return RebalancePlan(
            actions=actions,
            new_buy_opportunities=new_buy_opportunities,
            generated_at=datetime.now(timezone.utc),
            new_buy_opportunities_source=source,
        )

    def _find_new_buy_opportunities(self, holdings: List[HoldingAnalysis]):
        run = self._repository.get_latest_consumer_visible_run(self._session)
        if run is None:
            return [], _NO_SCAN_SOURCE

        records = self._repository.get_symbol_records_by_symbol(self._session, run.id)
        outcomes = [outcome_from_record(r) for r in records.values()]
        rankings = self._ranking_engine.rank(outcomes)

        held_symbols = {h.symbol for h in holdings}
        max_opportunities = get_max_new_buy_opportunities()

        seen = set()
        opportunities = []
        for category in (RankingCategory.TOP_STRONG_BUY, RankingCategory.TOP_BUY):
            for entry in rankings[category].entries:
                if entry.symbol in held_symbols or entry.symbol in seen:
                    continue
                seen.add(entry.symbol)
                opportunities.append(
                    NewBuyOpportunity(
                        symbol=entry.symbol,
                        sector=entry.sector,
                        recommendation=entry.recommendation,
                        confidence=entry.confidence,
                        final_score=entry.final_score,
                        rationale=(
                            f"Ranked {category.value.replace('_', ' ').title()} in market scan #{run.id} "
                            f"(final score {entry.final_score:.1f}/100, confidence "
                            f"{entry.confidence:.1f}%)." if entry.final_score is not None and entry.confidence is not None
                            else f"Ranked {category.value.replace('_', ' ').title()} in market scan #{run.id}."
                        ),
                    )
                )
                if len(opportunities) >= max_opportunities:
                    return opportunities, f"market_scan_run_{run.id}"

        return opportunities, f"market_scan_run_{run.id}"
