"""POST/GET/DELETE /api/v1/signals -- "متابعة هذه الإشارة" (follow this
signal) and the personal-vs-algorithm performance comparison, product
decision 2026-09-18. Every route resolves the target signal strictly
from `current_user.id` (never from a client-supplied user id), the
same IDOR defense already used by src.api.routes.watchlist.

2026-09-19 (full-platform audit): every route requires
`require_active_subscription()`, matching `src.api.routes.stocks`/
`radar`'s own convention -- `follow`/`get_followed` return the same
paid-tier entry-zone/target/stop-loss fields those routes already
gate behind an active subscription, so an unsubscribed account must
not be able to reach them by following a snapshot ID here instead.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.schemas.auth import MessageOut
from src.api.schemas.signals import (
    FollowedSignalListOut,
    FollowedSignalOut,
    FollowSignalRequest,
    PersonalPerformanceComparisonOut,
)
from src.auth.rbac import require_active_subscription
from src.core.db.database import get_db
from src.domain.models import User
from src.market_intelligence.followed_signals import (
    compute_personal_vs_algorithm_performance,
    follow_signal,
    list_followed_signals,
    unfollow_signal,
)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


def _item_out(record) -> FollowedSignalOut:
    return FollowedSignalOut(
        id=record.id,
        decision_v2_snapshot_id=record.decision_v2_snapshot_id,
        symbol=record.symbol,
        company_name_ar=record.company_name_ar,
        followed_at=record.followed_at,
        decision=record.decision,
        decision_label_ar=record.decision_label_ar,
        entry_zone_low=record.entry_zone_low,
        entry_zone_high=record.entry_zone_high,
        stop_loss=record.stop_loss,
        target_1=record.target_1,
        target_2=record.target_2,
        target_3=record.target_3,
        outcome_status=record.outcome_status,
        outcome_status_label_ar=record.outcome_status_label_ar,
        outcome_return_pct=record.outcome_return_pct,
    )


@router.post("/follow", response_model=FollowedSignalOut, status_code=201)
def follow(
    body: FollowSignalRequest,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> FollowedSignalOut:
    row = follow_signal(session, current_user.id, body.decision_v2_snapshot_id)
    records = list_followed_signals(session, current_user.id)
    record = next(r for r in records if r.id == row.id)
    return _item_out(record)


@router.delete("/{decision_v2_snapshot_id}", response_model=MessageOut)
def unfollow(
    decision_v2_snapshot_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> MessageOut:
    unfollow_signal(session, current_user.id, decision_v2_snapshot_id)
    return MessageOut(message="تم إلغاء متابعة هذه الإشارة.")


@router.get("/followed", response_model=FollowedSignalListOut)
def get_followed(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> FollowedSignalListOut:
    records = list_followed_signals(session, current_user.id)
    return FollowedSignalListOut(generated_at=datetime.now(timezone.utc), items=[_item_out(r) for r in records])


@router.get("/performance", response_model=PersonalPerformanceComparisonOut)
def get_performance(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription()),
) -> PersonalPerformanceComparisonOut:
    comparison = compute_personal_vs_algorithm_performance(session, current_user.id)
    return PersonalPerformanceComparisonOut(
        generated_at=comparison.generated_at,
        personal_resolved_sample_size=comparison.personal_resolved_sample_size,
        personal_win_rate_pct=comparison.personal_win_rate_pct,
        personal_small_sample_warning=comparison.personal_small_sample_warning,
        algorithm_resolved_sample_size=comparison.algorithm_resolved_sample_size,
        algorithm_win_rate_pct=comparison.algorithm_win_rate_pct,
        algorithm_small_sample_warning=comparison.algorithm_small_sample_warning,
        insufficient_data_message_ar=comparison.insufficient_data_message_ar,
    )
