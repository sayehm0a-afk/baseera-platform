"""The personal "امسح السوق الآن" (scan the market now) read path.

Deliberately reuses, and never re-runs, the existing scan pipeline:
`DecisionV2Snapshot` already carries one insert-only row per symbol per
`MarketScanRun` (written by `MarketIntelligenceRepository.
save_symbol_records`, alongside the same scan that populates every
other read route in `src/api/routes/market.py`). Reading it is a plain
DB query -- zero SAHMK requests, whether this is called once or a
thousand times a day, which is the whole point: pressing the button
must never trigger a fresh live scan (that would be one full-market
SAHMK pass -- ~370+ requests -- per press, against a 5000/day account
quota).

Two decisions this module encodes that a naive "top N by score" query
would miss:

1. Uniqueness is structural, not a client-side workaround. Unlike
   `GET /opportunities` (8 independently-ranked categories that can and
   do repeat a symbol across sections -- see opportunity_ranking.py),
   this module keeps at most one row per symbol: the most recent
   `DecisionV2Snapshot` for that symbol within the target scan run
   (`_latest_snapshot_per_symbol`), so the final list can never contain
   a duplicate by construction.
2. Staleness is disclosed, never silently presented as fresh. If the
   most recent successful scan is older than `get_max_data_age_hours()`
   (the same threshold `publication_gate.py`'s freshness gate already
   uses), no candidates are returned at all -- an honest
   "لا توجد بيانات كافية" state, not last week's picks relabeled as
   today's.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.analysis.decision_v2.types import Decision
from src.domain.models import DecisionV2Snapshot, MarketScanRun
from src.market_intelligence.config import get_max_data_age_hours

# Only these decisions represent a genuine trade-worthy opportunity
# (buy now, or a good setup worth waiting on) -- HOLD/REDUCE/EXIT/
# REJECT/INSUFFICIENT_DATA/WATCH are real Decision Engine V2 outputs
# but are not "opportunities" in the day-trading-scan sense this
# button answers. Order here also doubles as the tie-break priority
# (index 0 = ranked above every other decision at equal score).
_OPPORTUNITY_DECISIONS = (
    Decision.STRONG_BUY_CANDIDATE.value,
    Decision.BUY_CANDIDATE.value,
    Decision.WAIT_FOR_ENTRY.value,
)
_DECISION_PRIORITY = {value: index for index, value in enumerate(_OPPORTUNITY_DECISIONS)}


@dataclass(frozen=True)
class PersonalScanResult:
    scan_run: Optional[MarketScanRun]
    candidates: List[DecisionV2Snapshot]
    is_stale: bool
    data_age_hours: Optional[float]
    max_data_age_hours: float


def _latest_snapshot_per_symbol(snapshots: List[DecisionV2Snapshot]) -> List[DecisionV2Snapshot]:
    """Collapses possibly-multiple rows per symbol (this table is an
    insert-only request log -- see DecisionV2Snapshot's own docstring)
    down to the single most recent row per symbol, so the caller never
    has to dedupe again downstream."""
    best_by_symbol: Dict[str, DecisionV2Snapshot] = {}
    for snapshot in snapshots:
        existing = best_by_symbol.get(snapshot.symbol)
        if existing is None or snapshot.id > existing.id:
            best_by_symbol[snapshot.symbol] = snapshot
    return list(best_by_symbol.values())


def _sort_key(snapshot: DecisionV2Snapshot):
    priority = _DECISION_PRIORITY.get(snapshot.decision, len(_DECISION_PRIORITY))
    quality = float(snapshot.opportunity_quality_score) if snapshot.opportunity_quality_score is not None else 0.0
    confidence = float(snapshot.confidence_score) if snapshot.confidence_score is not None else 0.0
    # Lower risk_score is safer; used only as the final tie-break so it
    # never overrides the primary quality/confidence ranking.
    risk = float(snapshot.risk_score) if snapshot.risk_score is not None else 100.0
    return (priority, -quality, -confidence, risk)


def select_top_opportunities(
    session: Session,
    scan_run: Optional[MarketScanRun],
    max_results: int = 5,
    now: Optional[datetime] = None,
) -> PersonalScanResult:
    """Pure DB read -- no provider call, no re-scan. `scan_run=None`
    (no completed scan exists yet) and a stale `scan_run` both return
    an empty candidate list; the caller renders the appropriate Arabic
    "no data"/"no opportunity" message in either case (see
    `PersonalScanResult.is_stale` to tell them apart)."""
    max_age_hours = get_max_data_age_hours()
    now = now or datetime.now(timezone.utc)

    if scan_run is None or scan_run.finished_at is None:
        return PersonalScanResult(
            scan_run=scan_run, candidates=[], is_stale=True, data_age_hours=None, max_data_age_hours=max_age_hours
        )

    finished_at = scan_run.finished_at
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    age_hours = (now - finished_at).total_seconds() / 3600.0

    if age_hours > max_age_hours:
        return PersonalScanResult(
            scan_run=scan_run, candidates=[], is_stale=True, data_age_hours=age_hours, max_data_age_hours=max_age_hours
        )

    rows = (
        session.query(DecisionV2Snapshot)
        .filter(
            DecisionV2Snapshot.scan_run_id == scan_run.id,
            DecisionV2Snapshot.decision.in_(_OPPORTUNITY_DECISIONS),
        )
        .order_by(desc(DecisionV2Snapshot.id))
        .all()
    )
    deduped = _latest_snapshot_per_symbol(rows)
    ranked = sorted(deduped, key=_sort_key)[:max_results]

    return PersonalScanResult(
        scan_run=scan_run, candidates=ranked, is_stale=False, data_age_hours=age_hours, max_data_age_hours=max_age_hours
    )
