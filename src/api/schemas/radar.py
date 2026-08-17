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
