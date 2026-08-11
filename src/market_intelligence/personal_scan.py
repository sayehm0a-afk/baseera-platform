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


# Freshness is disclosed as one of four honest states, not a single
# stale/fresh boolean -- CONT Phase 6. FRESH and AGING both still
# return real candidates (the scan is within `max_data_age_hours`
# either way); the distinction is purely informational, so a trader
# nearing the staleness cutoff sees the data is getting old before it
# actually stops being usable, rather than a sudden "no data" cliff.
FRESHNESS_FRESH = "FRESH"
FRESHNESS_AGING = "AGING"
FRESHNESS_STALE = "STALE"
FRESHNESS_NO_SCAN = "NO_SCAN"

FRESHNESS_LABELS_AR = {
    FRESHNESS_FRESH: "بيانات حديثة",
    FRESHNESS_AGING: "بيانات آخذة في التقادم لكنها لا تزال مفيدة",
    FRESHNESS_STALE: "بيانات قديمة جدًا لإصدار توصية جديدة",
    FRESHNESS_NO_SCAN: "لا يوجد مسح سابق للسوق",
}

# The fraction of max_data_age_hours after which still-usable data is
# disclosed as "aging" rather than simply "fresh" -- halfway through
# the freshness budget is the natural, unambiguous midpoint; not tied
# to any other threshold in the codebase.
_AGING_THRESHOLD_FRACTION = 0.5


def _classify_freshness(is_stale: bool, data_age_hours: Optional[float], max_data_age_hours: float) -> str:
    if data_age_hours is None:
        return FRESHNESS_NO_SCAN
    if is_stale:
        return FRESHNESS_STALE
    if data_age_hours > max_data_age_hours * _AGING_THRESHOLD_FRACTION:
        return FRESHNESS_AGING
    return FRESHNESS_FRESH


@dataclass(frozen=True)
class PersonalScanResult:
    scan_run: Optional[MarketScanRun]
    candidates: List[DecisionV2Snapshot]
    is_stale: bool
    data_age_hours: Optional[float]
    max_data_age_hours: float
    freshness_state: str
    freshness_label_ar: str


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


# Entry-readiness points -- how immediately actionable the entry is,
# not just whether Decision Engine V2 classified it a "candidate."
# READY_NOW earns the biggest bonus; MISSED_ENTRY (the price already
# ran past a sane entry zone) is penalized even though the underlying
# decision may still be BUY_CANDIDATE. CONDITIONAL_ON_BREAKOUT and an
# unset entry_status are treated as neutral (0) -- no real evidence
# either way, never guessed.
_ENTRY_READINESS_POINTS = {
    "READY_NOW": 10.0,
    "NEAR_ENTRY": 5.0,
    "WAIT_FOR_PULLBACK": 0.0,
    "MISSED_ENTRY": -15.0,
}

_NEWS_IMPACT_POINTS = {"POSITIVE": 5.0, "NEGATIVE": -8.0}

# Each entry in why_not_buy_reasons is one real, named caveat Decision
# Engine V2 itself surfaced about this exact candidate (see
# DecisionResult.why_not_buy_reasons) -- a small per-reason penalty so
# a candidate with several disclosed caveats ranks below an otherwise
# similar one with none, without ever hiding or discarding the caveats
# themselves (still shown in full via the transparency panel).
_CONTRADICTION_PENALTY_PER_REASON = -2.0
_CONTRADICTION_PENALTY_CAP = -10.0

# Percent-of-price distance from the invalidation level below which a
# candidate is penalized for being "one bad tick from invalidated" --
# real evidence (invalidation_price vs. current_price), not a guess.
_INVALIDATION_PROXIMITY_TIGHT_PCT = 2.0
_INVALIDATION_PROXIMITY_NEAR_PCT = 5.0


def _composite_score(snapshot: DecisionV2Snapshot) -> float:
    """A single ranking score blending every real, already-computed
    Decision Engine V2 signal this module has access to -- not just
    quality+confidence. Higher is better. Every component degrades to
    a neutral (0) contribution when its underlying field is null,
    never a guessed value standing in for missing evidence."""
    quality = float(snapshot.opportunity_quality_score) if snapshot.opportunity_quality_score is not None else 0.0
    confidence = float(snapshot.confidence_score) if snapshot.confidence_score is not None else 0.0
    risk = float(snapshot.risk_score) if snapshot.risk_score is not None else 50.0

    score = quality * 0.30 + confidence * 0.25 + (100.0 - risk) * 0.10

    if snapshot.risk_reward_target_1 is not None:
        risk_reward = min(float(snapshot.risk_reward_target_1), 5.0)
        score += (risk_reward / 5.0) * 100.0 * 0.15

    score += _ENTRY_READINESS_POINTS.get(snapshot.entry_status, 0.0)
    score += _NEWS_IMPACT_POINTS.get(snapshot.news_impact, 0.0)

    if snapshot.volume_confirms_decision is True:
        score += 5.0
    if snapshot.abnormal_volume is True:
        score -= 5.0

    if snapshot.market_risk_entry_permitted is False:
        score -= 10.0

    reasons = snapshot.why_not_buy_reasons or []
    score += max(len(reasons) * _CONTRADICTION_PENALTY_PER_REASON, _CONTRADICTION_PENALTY_CAP)

    if snapshot.current_price is not None and snapshot.invalidation_price is not None and snapshot.current_price:
        distance_pct = abs(float(snapshot.current_price) - float(snapshot.invalidation_price)) / float(
            snapshot.current_price
        ) * 100.0
        if distance_pct < _INVALIDATION_PROXIMITY_TIGHT_PCT:
            score -= 10.0
        elif distance_pct < _INVALIDATION_PROXIMITY_NEAR_PCT:
            score -= 5.0

    return score


def _sort_key(snapshot: DecisionV2Snapshot):
    priority = _DECISION_PRIORITY.get(snapshot.decision, len(_DECISION_PRIORITY))
    # Symbol as the final, fully deterministic tie-break -- two
    # candidates scoring exactly equal must still sort the same way on
    # every call, never depend on dict/query iteration order.
    return (priority, -_composite_score(snapshot), snapshot.symbol)


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
            scan_run=scan_run, candidates=[], is_stale=True, data_age_hours=None, max_data_age_hours=max_age_hours,
            freshness_state=FRESHNESS_NO_SCAN, freshness_label_ar=FRESHNESS_LABELS_AR[FRESHNESS_NO_SCAN],
        )

    finished_at = scan_run.finished_at
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    age_hours = (now - finished_at).total_seconds() / 3600.0

    if age_hours > max_age_hours:
        return PersonalScanResult(
            scan_run=scan_run, candidates=[], is_stale=True, data_age_hours=age_hours, max_data_age_hours=max_age_hours,
            freshness_state=FRESHNESS_STALE, freshness_label_ar=FRESHNESS_LABELS_AR[FRESHNESS_STALE],
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

    freshness_state = _classify_freshness(False, age_hours, max_age_hours)
    return PersonalScanResult(
        scan_run=scan_run, candidates=ranked, is_stale=False, data_age_hours=age_hours, max_data_age_hours=max_age_hours,
        freshness_state=freshness_state, freshness_label_ar=FRESHNESS_LABELS_AR[freshness_state],
    )
