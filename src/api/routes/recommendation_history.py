"""GET /api/v1/recommendations/history[/stats] -- the platform's real,
append-only recommendation track record (RecommendationSnapshot +
RecommendationOutcome). Available to every authenticated user: this is
not personal data (no user_id on either table), it is Basirah's own
public track record, and hiding it from ordinary users while showing
it to staff would be exactly the "hide the losses" failure mode this
milestone explicitly forbids.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.api.schemas.recommendation_history import (
    RecommendationHistoryItemOut,
    RecommendationHistoryListOut,
    RecommendationHistoryStatsOut,
    RecommendationOutcomeOut,
)
from src.ai_evolution.outcome_evaluation import EVALUATION_HORIZON_DAYS
from src.core.db.database import get_db
from src.domain.models import (
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
    User,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

_TERMINAL_STATUSES = {
    RecommendationOutcomeStatus.SUCCESSFUL,
    RecommendationOutcomeStatus.FAILED,
    RecommendationOutcomeStatus.PARTIAL,
    RecommendationOutcomeStatus.EXPIRED,
    RecommendationOutcomeStatus.CANCELLED,
}


def outcome_out(outcome: RecommendationOutcome) -> RecommendationOutcomeOut:
    return RecommendationOutcomeOut(
        evaluation_horizon_days=outcome.evaluation_horizon_days,
        status=outcome.status.value,
        due_at=outcome.due_at,
        evaluated_at=outcome.evaluated_at,
        price_at_evaluation=float(outcome.price_at_evaluation) if outcome.price_at_evaluation is not None else None,
        return_pct=float(outcome.return_pct) if outcome.return_pct is not None else None,
        hit_target=outcome.hit_target,
        hit_stop=outcome.hit_stop,
        target_1_reached=outcome.target_1_reached,
        target_1_reached_at=outcome.target_1_reached_at,
        target_2_reached=outcome.target_2_reached,
        target_2_reached_at=outcome.target_2_reached_at,
        target_3_reached=outcome.target_3_reached,
        target_3_reached_at=outcome.target_3_reached_at,
        max_favorable_excursion_pct=(
            float(outcome.max_favorable_excursion_pct) if outcome.max_favorable_excursion_pct is not None else None
        ),
        max_adverse_excursion_pct=(
            float(outcome.max_adverse_excursion_pct) if outcome.max_adverse_excursion_pct is not None else None
        ),
        time_to_target_days=outcome.time_to_target_days,
    )


def overall_status(snapshot: RecommendationSnapshot, outcomes: List[RecommendationOutcome]) -> str:
    if not outcomes:
        return "NO_OUTCOMES_TRACKED"
    pending_exists = any(o.status == RecommendationOutcomeStatus.PENDING for o in outcomes)
    if not pending_exists:
        return "COMPLETED"
    if snapshot.expires_at is not None and snapshot.expires_at < datetime.now(timezone.utc):
        return "EXPIRED"
    return "ACTIVE"


def history_item_out(
    snapshot: RecommendationSnapshot, stock: Optional[Stock], outcomes: List[RecommendationOutcome]
) -> RecommendationHistoryItemOut:
    return RecommendationHistoryItemOut(
        id=snapshot.id,
        symbol=snapshot.symbol,
        company_name_ar=stock.name_ar if stock else None,
        sector=stock.sector if stock else None,
        evaluated_at=snapshot.evaluated_at,
        recommendation=snapshot.recommendation.value,
        confidence_score=float(snapshot.confidence_score),
        calibrated_confidence_score=(
            float(snapshot.calibrated_confidence_score) if snapshot.calibrated_confidence_score is not None else None
        ),
        market_price_at_evaluation=(
            float(snapshot.market_price_at_evaluation) if snapshot.market_price_at_evaluation is not None else None
        ),
        target_price=float(snapshot.target_price) if snapshot.target_price is not None else None,
        target_price_2=float(snapshot.target_price_2) if snapshot.target_price_2 is not None else None,
        target_price_3=float(snapshot.target_price_3) if snapshot.target_price_3 is not None else None,
        stop_loss=float(snapshot.stop_loss) if snapshot.stop_loss is not None else None,
        expected_return_pct=float(snapshot.expected_return_pct) if snapshot.expected_return_pct is not None else None,
        time_horizon=snapshot.time_horizon,
        risk_level=snapshot.risk_level,
        position_size=snapshot.position_size,
        expires_at=snapshot.expires_at,
        reasons=list(snapshot.reasons or []),
        engine_version=snapshot.engine_version,
        is_paper_trade=snapshot.is_paper_trade,
        overall_status=overall_status(snapshot, outcomes),
        outcomes=[outcome_out(o) for o in outcomes],
    )


def fetch_snapshots_with_context(
    session: Session,
    symbol: Optional[str],
    limit: int,
    offset: int,
):
    """Reusable raw-object fetch (snapshot, stock, its outcomes) --
    both the public /recommendations/history route and the staff-only
    /admin/recommendation-history route (which adds internal fields
    like contributor_breakdown) build on this same query, never a
    second parallel implementation."""
    query = session.query(RecommendationSnapshot).filter(RecommendationSnapshot.is_paper_trade.is_(False))
    if symbol:
        query = query.filter(RecommendationSnapshot.symbol == symbol)
    snapshots = query.order_by(RecommendationSnapshot.evaluated_at.desc()).offset(offset).limit(limit).all()

    if not snapshots:
        return []

    stock_ids = {s.stock_id for s in snapshots}
    stocks_by_id = {s.id: s for s in session.query(Stock).filter(Stock.id.in_(stock_ids)).all()}

    snapshot_ids = [s.id for s in snapshots]
    outcomes = (
        session.query(RecommendationOutcome)
        .filter(RecommendationOutcome.snapshot_id.in_(snapshot_ids))
        .order_by(RecommendationOutcome.evaluation_horizon_days.asc())
        .all()
    )
    outcomes_by_snapshot: dict = {}
    for outcome in outcomes:
        outcomes_by_snapshot.setdefault(outcome.snapshot_id, []).append(outcome)

    return [(s, stocks_by_id.get(s.stock_id), outcomes_by_snapshot.get(s.id, [])) for s in snapshots]


def _query_history(
    session: Session,
    symbol: Optional[str],
    status: Optional[str],
    limit: int,
    offset: int,
) -> List[RecommendationHistoryItemOut]:
    rows = fetch_snapshots_with_context(session, symbol, limit, offset)
    items = [history_item_out(snapshot, stock, outcomes) for snapshot, stock, outcomes in rows]
    if status:
        items = [item for item in items if item.overall_status == status]
    return items


@router.get("/history", response_model=RecommendationHistoryListOut)
def get_recommendation_history(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="ACTIVE | COMPLETED | EXPIRED | NO_OUTCOMES_TRACKED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> RecommendationHistoryListOut:
    items = _query_history(session, symbol, status, limit, offset)
    return RecommendationHistoryListOut(generated_at=datetime.now(timezone.utc), total=len(items), items=items)


@router.get("/history/stats", response_model=RecommendationHistoryStatsOut)
def get_recommendation_history_stats(
    evaluation_horizon_days: int = Query(7),
    session: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> RecommendationHistoryStatsOut:
    if evaluation_horizon_days not in EVALUATION_HORIZON_DAYS:
        evaluation_horizon_days = 7

    outcomes = (
        session.query(RecommendationOutcome)
        .filter(RecommendationOutcome.evaluation_horizon_days == evaluation_horizon_days)
        .all()
    )
    sample_size = len(outcomes)
    terminal = [o for o in outcomes if o.status in _TERMINAL_STATUSES]
    terminal_sample_size = len(terminal)

    status_counts: dict = {}
    for outcome in outcomes:
        status_counts[outcome.status.value] = status_counts.get(outcome.status.value, 0) + 1

    win_rate = None
    average_return_pct = None
    target_hit_rate = None
    stop_hit_rate = None
    if terminal_sample_size > 0:
        successful = sum(1 for o in terminal if o.status == RecommendationOutcomeStatus.SUCCESSFUL)
        win_rate = round(successful / terminal_sample_size * 100, 2)
        returns = [float(o.return_pct) for o in terminal if o.return_pct is not None]
        if returns:
            average_return_pct = round(sum(returns) / len(returns), 4)
        hit_target_count = sum(1 for o in terminal if o.hit_target)
        hit_stop_count = sum(1 for o in terminal if o.hit_stop)
        target_hit_rate = round(hit_target_count / terminal_sample_size * 100, 2)
        stop_hit_rate = round(hit_stop_count / terminal_sample_size * 100, 2)

    return RecommendationHistoryStatsOut(
        generated_at=datetime.now(timezone.utc),
        evaluation_horizon_days=evaluation_horizon_days,
        sample_size=sample_size,
        terminal_sample_size=terminal_sample_size,
        win_rate=win_rate,
        average_return_pct=average_return_pct,
        target_hit_rate=target_hit_rate,
        stop_hit_rate=stop_hit_rate,
        status_counts=status_counts,
        # Below this, a single outcome swings the percentage by double
        # digits -- shown, never hidden, but flagged so the frontend
        # never presents it as a reliable track record.
        small_sample_warning=terminal_sample_size < 30,
    )
