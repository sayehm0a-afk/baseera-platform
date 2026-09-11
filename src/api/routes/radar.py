"""GET/POST /api/v1/radar/* -- consumer-facing Smart Radar layer.

Basirah Radar V2 mandate (Phase B/D, 2026-08-17): expose the same real
`RadarOpportunity`/Decision V2 intelligence the staff-only routes in
`src.api.routes.admin.market_intelligence` already serve, to ordinary
authenticated subscribers -- without creating a second scoring engine,
a second query, or a second formatter. Every GET route here:

  * reads only already-persisted Postgres rows (`RadarOpportunity`,
    `DecisionV2Snapshot`, the most recent completed `MarketScanRun`'s
    breadth) -- never calls `get_market_data_provider()` or any SAHMK
    client method, so page views of this router spend zero SAHMK quota,
    matching every other consumer market-data route's contract
    (see `src.api.routes.market`'s own module docstring).
  * reuses `radar_summary_out`/`radar_detail_out` (the exact formatter
    functions the staff routes use) and `list_live_opportunities`
    (the exact query the staff `/radar-v2/opportunities` route uses) --
    both promoted to public/importable in this same change, not
    reimplemented here.
  * requires `require_active_subscription()`, the same auth dependency
    every other consumer market-data route in `src.api.routes.market`
    uses -- staff-only diagnostics (SAHMK consumption, raw scan
    internals) stay exclusively on the `/admin/market-intelligence/*`
    routes and are never exposed here.
  * returns an honest empty state (`live_opportunity_count=0`, an empty
    list) when no real `RadarOpportunity` rows exist yet -- never a
    fabricated opportunity.

`GET /summary` additionally reuses `classify_market_risk` (a pure,
DB-derived function -- see `src.analysis.decision_v2.market_risk`) and
`get_market_status` (the calendar-only session check `src.api.routes.
market`'s own `/status` route computes before its separate live
provider-health probe) so the "is the market receptive to new entries
right now" read stays honest without adding a live provider call of its
own -- this route deliberately does not replicate `/market/status`'s
`health_check()` probe.

`POST /scan-now` (2026-09-11, on-demand consumer scan mandate) is the
one route here that is NOT zero-SAHMK-cost by design: it lets an
authenticated subscriber claim one turn of the exact same bounded,
quota-gated, leader-locked cycle the staff `/admin/market-intelligence/
radar-v2/scan` route and the recurring scheduler already run, via the
shared `run_one_bounded_background_cycle`/`run_radar_v2_cycle` --
tagged `CONSUMER_SCAN_NOW` for separate SAHMK attribution, and gated by
an additional per-user cooldown (`get_radar_scan_now_cooldown_seconds`)
on top of every quota/leader-lock/health guard that helper already
enforces. No new scan logic, ranking, or scoring exists here -- only a
new caller of an already-tested pipeline.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.analysis.decision_v2.decision_freshness import is_decision_fresh
from src.analysis.decision_v2.market_risk import classify_market_risk
from src.api.middleware.rate_limiting import limiter
from src.api.routes.admin.market_intelligence import (
    radar_detail_out,
    radar_summary_out,
    run_one_bounded_background_cycle,
)
from src.api.schemas.market_intelligence import RadarOpportunityDetailOut, RadarOpportunitySummaryOut
from src.api.schemas.radar import RadarHomeSummaryOut, RadarScanNowOut
from src.auth.rbac import require_active_subscription
from src.auth.token_store import get_redis_client
from src.core.db.database import get_db
from src.domain.models import DecisionV2Outcome, RadarOpportunity, User
from src.market_data.sahmk.operation_scope import CONSUMER_SCAN_NOW
from src.market_intelligence.config import get_radar_scan_now_cooldown_seconds, get_radar_stage2_candidate_cap
from src.market_intelligence.market_status import MarketSessionStatus, get_market_status, market_status_label_ar
from src.market_intelligence.radar_v2 import list_live_opportunities, run_radar_v2_cycle
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])

logger = logging.getLogger(__name__)

_SCAN_NOW_COOLDOWN_KEY_PREFIX = "basirah:radar:scan_now_cooldown"

_repository = MarketIntelligenceRepository()

# Small, fixed size for the home-screen preview -- the full ranked list
# is available via GET /opportunities; this only needs enough to render
# the home screen without a second round trip.
_HOME_TOP_OPPORTUNITIES_LIMIT = 5


def _latest_market_breadth(session: Session):
    """Best-effort, never-raising read of the most recent completed
    scan run's breadth -- identical convention to `src.api.routes.
    stocks._latest_market_breadth` and `src.api.routes.market`'s own
    use of the same repository method; a missing/failed lookup degrades
    to `None`, which `classify_market_risk` already handles honestly as
    INSUFFICIENT_DATA rather than failing the whole request."""
    try:
        run = _repository.get_latest_consumer_visible_run(session)
        if run is None:
            return None
        return _repository.get_market_breadth(session, run.id)
    except Exception:  # noqa: BLE001 -- a breadth-read failure must never break /radar/summary
        return None


@router.get("/summary", response_model=RadarHomeSummaryOut)
@limiter.limit("30/minute")
def get_radar_summary(
    request: Request,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_active_subscription()),
) -> RadarHomeSummaryOut:
    """Everything the Smart Radar home screen needs in one call: the
    radar's current live composition, the market-wide entry-risk read,
    and a short top-ranked preview -- all read from already-persisted
    state, zero SAHMK cost."""
    # Production truthfulness fix (2026-08-23): `list_live_opportunities()`
    # only excludes a symbol's superseded radar entries -- it does not (and,
    # being shared with the staff admin routes' own full-visibility needs,
    # should not) exclude a decision that has simply gone STALE with age.
    # A radar entry whose Decision V2 snapshot is no longer fresh for the
    # current session must not count toward, or occupy a preview slot in,
    # what this consumer-facing summary calls "live" -- confirmed in
    # production (2026-08-23T13:04Z diagnostic): symbol 6060, emitted
    # 2026-08-20 (STALE), was still surfacing in `top_opportunities` with
    # entry_status=READY_NOW, rendering as an actionable BUY three days
    # after its signal. No Decision V2/scoring/ranking logic changes --
    # `list_live_opportunities()`'s query and ordering are untouched; this
    # only filters the already-fetched, already-ranked Python list before
    # it is summarized/previewed.
    live_all = list_live_opportunities(session, limit=1000)
    live = [o for o in live_all if is_decision_fresh(o.emitted_at)]
    by_classification: Dict[str, int] = {}
    for o in live:
        by_classification[o.classification] = by_classification.get(o.classification, 0) + 1
    average_confidence = (
        round(sum(float(o.confidence_score) for o in live) / len(live), 1) if live else None
    )
    most_recent = max(live, key=lambda o: o.emitted_at, default=None)

    status_info = get_market_status()
    market_is_open = status_info.status == MarketSessionStatus.OPEN
    breadth = _latest_market_breadth(session)
    risk = classify_market_risk(market_is_open=market_is_open, breadth=breadth)

    top = live[:_HOME_TOP_OPPORTUNITIES_LIMIT]

    latest_stage1_run = _repository.get_latest_run_with_stage1_metrics(session)
    final_opportunities_count = (
        session.query(RadarOpportunity).filter_by(scan_run_id=latest_stage1_run.id).count()
        if latest_stage1_run is not None
        else None
    )

    return RadarHomeSummaryOut(
        generated_at=datetime.now(timezone.utc),
        live_opportunity_count=len(live),
        live_by_classification=by_classification,
        average_confidence=average_confidence,
        most_recent_emitted_at=most_recent.emitted_at if most_recent else None,
        market_status=status_info.status.value,
        market_status_label_ar=market_status_label_ar(status_info.status.value),
        market_risk_state=risk.state.value,
        market_risk_label_ar=risk.label_ar,
        market_risk_basis_ar=risk.basis_ar,
        entry_permitted=risk.entry_permitted,
        market_risk_is_live=risk.is_live,
        top_opportunities=[radar_summary_out(o) for o in top],
        stage1_universe_size=latest_stage1_run.stage1_universe_size if latest_stage1_run else None,
        stage1_evaluated_count=latest_stage1_run.stage1_evaluated_count if latest_stage1_run else None,
        stage1_candidate_count=latest_stage1_run.stage1_candidate_count if latest_stage1_run else None,
        stage2_candidate_cap=get_radar_stage2_candidate_cap(),
        stage2_validated_count=latest_stage1_run.symbols_succeeded if latest_stage1_run else None,
        final_opportunities_count=final_opportunities_count,
        last_full_scan_at=latest_stage1_run.finished_at if latest_stage1_run else None,
    )


@router.get("/opportunities", response_model=List[RadarOpportunitySummaryOut])
@limiter.limit("30/minute")
def list_radar_opportunities(
    request: Request,
    classification: Optional[str] = Query(default=None, description="Filter to one classification value, e.g. BUY_CANDIDATE."),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_active_subscription()),
) -> List[RadarOpportunitySummaryOut]:
    """The current, ranked Smart Radar list -- only each symbol's live
    opportunity (`superseded_by_id IS NULL`) appears, ordered by
    stage1_ranking_score descending. Returns an empty list, never a
    fabricated one, when no real opportunity has been emitted yet."""
    rows = list_live_opportunities(session, classification=classification, limit=limit)
    return [radar_summary_out(o) for o in rows]


@router.get("/opportunities/{opportunity_id}", response_model=RadarOpportunityDetailOut)
@limiter.limit("30/minute")
def get_radar_opportunity(
    request: Request,
    opportunity_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_active_subscription()),
) -> RadarOpportunityDetailOut:
    """Full consumer-safe evidence for one radar opportunity -- the same
    fields the staff detail route returns (Stage 1 ranking breakdown,
    reasoning, risk flags, tracked outcome once real forward market data
    exists); see `RadarOpportunityDetailOut`'s own docstring for exactly
    which fields this does and does not include."""
    opportunity = session.query(RadarOpportunity).filter_by(id=opportunity_id).first()
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Radar opportunity not found.")
    outcome = (
        session.query(DecisionV2Outcome)
        .filter_by(decision_v2_snapshot_id=opportunity.decision_v2_snapshot_id)
        .first()
    )
    return radar_detail_out(opportunity, outcome)


@router.post("/scan-now", response_model=RadarScanNowOut)
@limiter.limit("10/minute")
async def trigger_radar_scan_now(
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> RadarScanNowOut:
    """Consumer-triggered on-demand Radar V2 pass. Claims a per-user
    cooldown slot in Redis (NX+EX, so concurrent double-clicks from the
    same user race safely) BEFORE attempting the cycle; a claimed slot
    is spent regardless of whether the cycle actually executes (e.g. it
    may still refuse with `background_quota_low`/`scan_in_progress`/
    `not_leader`) -- those attempts still cost a real leader-lock
    compare-and-swap plus DB/Redis health probes, so charging the
    cooldown for them too, not only for a successful run, is what
    actually bounds one user's worst-case load on those shared
    resources. `@limiter.limit("10/minute")` (per network address, this
    router's existing convention) is a coarse anti-hammering backstop
    only -- the per-user Redis cooldown above is the real usage cap.

    Fails closed on a Redis error (`stop_reason="redis_unavailable"`):
    refusing to run an unbounded on-demand scan is the safe default,
    the same posture `SchedulerLeaderLock` already takes for the
    identical reason (see that module's own docstring)."""
    triggered_at = datetime.now(timezone.utc)
    cooldown_seconds = get_radar_scan_now_cooldown_seconds()
    cooldown_key = f"{_SCAN_NOW_COOLDOWN_KEY_PREFIX}:{current_user.id}"
    redis_client = get_redis_client()

    try:
        claimed = bool(redis_client.set(cooldown_key, "1", nx=True, ex=cooldown_seconds))
    except Exception:
        logger.error("scan-now: Redis cooldown check failed -- refusing (fail closed).", exc_info=True)
        return RadarScanNowOut(triggered_at=triggered_at, executed=False, stop_reason="redis_unavailable")

    if not claimed:
        try:
            ttl = redis_client.ttl(cooldown_key)
        except Exception:
            ttl = cooldown_seconds
        retry_after = ttl if ttl and ttl > 0 else cooldown_seconds
        return RadarScanNowOut(
            triggered_at=triggered_at,
            executed=False,
            stop_reason="cooldown_active",
            retry_after_seconds=retry_after,
        )

    result = await run_radar_v2_cycle(
        session,
        lambda s, caller, resolve_symbols: run_one_bounded_background_cycle(
            s, caller, resolve_symbols, operation=CONSUMER_SCAN_NOW
        ),
    )
    return RadarScanNowOut(
        triggered_at=triggered_at,
        executed=result.stage2_executed,
        stop_reason=result.stage2_stop_reason,
        opportunities_emitted_count=len(result.opportunities_emitted),
    )
