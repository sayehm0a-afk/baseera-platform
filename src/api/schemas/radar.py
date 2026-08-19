"""Schemas for the consumer-facing Smart Radar API
(`src.api.routes.radar`).

Deliberately reuses `RadarOpportunitySummaryOut`/`RadarOpportunityDetailOut`
from `src.api.schemas.market_intelligence` as-is rather than defining a
parallel "consumer" shape -- those schemas were already audited and
contain no staff-only/sensitive fields (see that module's own
docstrings), so importing them here is the reuse-first move, not a
duplication.

`RadarHomeSummaryOut` is the one genuinely new shape: a single-call
"Smart Radar home" payload combining the radar's live composition
(from `RadarOpportunity` rows) with the market-wide entry-risk read
(`src.analysis.decision_v2.market_risk.classify_market_risk`, itself
DB-only) and a short list of the top-ranked live opportunities, so the
frontend home screen needs one round trip, not several.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from src.api.schemas.market_intelligence import RadarOpportunitySummaryOut


class RadarHomeSummaryOut(BaseModel):
    """GET /api/v1/radar/summary -- everything the Smart Radar home
    screen needs in one read-only, zero-SAHMK-cost call."""

    generated_at: datetime

    live_opportunity_count: int
    live_by_classification: Dict[str, int] = Field(default_factory=dict)
    average_confidence: Optional[float] = None
    most_recent_emitted_at: Optional[datetime] = None

    market_status: str
    market_status_label_ar: str

    market_risk_state: str
    market_risk_label_ar: str
    market_risk_basis_ar: str
    entry_permitted: bool
    market_risk_is_live: bool

    top_opportunities: List[RadarOpportunitySummaryOut] = Field(default_factory=list)

    # Radar V2's real, dynamic scan funnel (BASIRAH mandate Phase 2 --
    # "never static"), from the most recent completed Radar V2 cycle:
    #   universe_total        -> Stage 1's full local Saudi-market universe
    #   universe_analyzable   -> of those, how many had enough price history
    #                            to actually be scored (Stage 1's evaluated_count)
    #   stage1_candidates     -> passed Stage 1's liquidity + signal filter
    #   stage2_validated      -> of the (<=stage2_candidate_cap) candidates sent
    #                            to Stage 2, how many a real live quote succeeded for
    #   final_opportunities   -> real RadarOpportunity rows that cycle emitted
    # Every field is None, never a fabricated 0, until a real Radar V2
    # cycle has completed. See `src.market_intelligence.radar_v2.
    # run_radar_v2_cycle` and `MarketIntelligenceRepository.
    # get_latest_run_with_stage1_metrics`.
    stage1_universe_size: Optional[int] = None
    stage1_evaluated_count: Optional[int] = None
    stage1_candidate_count: Optional[int] = None
    stage2_candidate_cap: int
    stage2_validated_count: Optional[int] = None
    final_opportunities_count: Optional[int] = None
    last_full_scan_at: Optional[datetime] = None
