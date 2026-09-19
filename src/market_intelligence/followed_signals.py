"""Follow-signal ("متابعة هذه الإشارة") + personal-vs-algorithm
performance comparison -- product decision 2026-09-18, after the owner
asked for a feature comparable to a competitor app: a user commits to
one specific, already-issued BUY recommendation, and the app later
shows whether it actually won or lost using the exact same real
outcome-tracking data already produced for every decision (see
`src.ai_evolution.decision_v2_outcome_evaluation`) -- nothing here
recomputes or re-evaluates an outcome, it only reads what has already
been independently, honestly tracked.

Win/loss definition mirrors `src.ai_evolution.validation_metrics`
exactly (`_TARGET_STATUSES`/`_STOP_STATUS`/`decisive`), so a user's
personal win rate and the algorithm's aggregate win rate are always
computed the same way and are genuinely comparable. `PARTIAL` (a
same-bar target/stop tie) and every other non-terminal/non-decisive
status (`PENDING`, `DATA_UNAVAILABLE`, `ENTRY_NEVER_TRIGGERED`,
`INVALIDATED`, `CANCELLED`, `EXPIRED`) are excluded from win-rate math
on both sides, never folded into either side to inflate a sample.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.ai_evolution.decision_v2_outcome_evaluation import is_actionable_buy_decision
from src.api.exceptions import (
    SignalAlreadyFollowedError,
    SignalNotActionableError,
    SignalSnapshotNotFoundError,
)
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    UserFollowedSignal,
)

# Never reported as a win, a loss, or excluded silently without being
# named -- kept in sync with validation_metrics.py's own constants.
_TARGET_STATUSES = (
    DecisionV2OutcomeStatus.TARGET_1_HIT,
    DecisionV2OutcomeStatus.TARGET_2_HIT,
    DecisionV2OutcomeStatus.TARGET_3_HIT,
)
_STOP_STATUS = DecisionV2OutcomeStatus.STOP_LOSS_HIT

# A group's win rate is only reported once at least this many resolved
# (decisive) outcomes back it -- matches the MIN_GROUP_SAMPLE_SIZE
# convention already used by personal_performance.py/sector_reliability.py.
MIN_RESOLVED_SAMPLE_SIZE = 10

# 2026-09-19 (full-platform audit): the algorithm-wide win rate is a
# platform-level track-record claim, not a per-user/per-group figure --
# it must meet the SAME statistical bar this platform already enforces
# for exactly that kind of claim (src.api.routes.recommendation_history's
# `small_sample_warning=terminal_sample_size < 30`), not the lower
# per-user bar above. Before this, `algorithm_win_rate_pct` was shown as
# an unqualified headline number even when the platform's own resolved
# sample was still below the 30-outcome floor it treats as reliable
# everywhere else -- the exact statistical-honesty gap this platform's
# own 2026-09-11 audit flagged for the overall success-rate figure.
ALGORITHM_MIN_RESOLVED_SAMPLE_SIZE = 30

_INSUFFICIENT_DATA_AR = "بيانات غير كافية بعد لعرض هذا المقياس بشكل موثوق"

OUTCOME_STATUS_LABEL_AR = {
    DecisionV2OutcomeStatus.PENDING: "قيد المتابعة",
    DecisionV2OutcomeStatus.TARGET_1_HIT: "تحقق الهدف الأول",
    DecisionV2OutcomeStatus.TARGET_2_HIT: "تحقق الهدف الثاني",
    DecisionV2OutcomeStatus.TARGET_3_HIT: "تحقق الهدف الثالث",
    DecisionV2OutcomeStatus.STOP_LOSS_HIT: "تم الوصول لوقف الخسارة",
    DecisionV2OutcomeStatus.PARTIAL: "نتيجة غير حاسمة (تلامس الهدف ووقف الخسارة في نفس الجلسة)",
    DecisionV2OutcomeStatus.EXPIRED: "انتهت المدة دون تحقيق الهدف أو وقف الخسارة",
    DecisionV2OutcomeStatus.CANCELLED: "تم إلغاء التوصية",
    DecisionV2OutcomeStatus.DATA_UNAVAILABLE: "تعذر تتبع النتيجة الحقيقية لعدم توفر بيانات كافية",
    DecisionV2OutcomeStatus.ENTRY_NEVER_TRIGGERED: "لم يصل السعر إلى نطاق الدخول",
    DecisionV2OutcomeStatus.INVALIDATED: "انتهت الفرصة قبل الدخول",
}


@dataclass(frozen=True)
class FollowedSignalRecord:
    id: int
    decision_v2_snapshot_id: int
    symbol: str
    company_name_ar: Optional[str]
    followed_at: datetime
    decision: str
    decision_label_ar: str
    entry_zone_low: Optional[float]
    entry_zone_high: Optional[float]
    stop_loss: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    target_3: Optional[float]
    outcome_status: Optional[str]
    outcome_status_label_ar: Optional[str]
    outcome_return_pct: Optional[float]


@dataclass(frozen=True)
class PersonalPerformanceComparison:
    generated_at: datetime
    personal_resolved_sample_size: int
    personal_win_rate_pct: Optional[float]
    personal_small_sample_warning: bool
    algorithm_resolved_sample_size: int
    algorithm_win_rate_pct: Optional[float]
    algorithm_small_sample_warning: bool
    insufficient_data_message_ar: Optional[str]


def follow_signal(session: Session, user_id: int, decision_v2_snapshot_id: int) -> UserFollowedSignal:
    snapshot = session.query(DecisionV2Snapshot).filter_by(id=decision_v2_snapshot_id).first()
    if snapshot is None:
        raise SignalSnapshotNotFoundError(f"لا يوجد تحليل بالمعرف '{decision_v2_snapshot_id}'.")

    if not is_actionable_buy_decision(snapshot.decision):
        raise SignalNotActionableError(
            "لا يمكن متابعة هذا التحليل لأنه ليس توصية شراء صريحة."
        )

    existing = (
        session.query(UserFollowedSignal)
        .filter_by(user_id=user_id, decision_v2_snapshot_id=decision_v2_snapshot_id)
        .first()
    )
    if existing is not None:
        raise SignalAlreadyFollowedError("أنت تتابع هذه الإشارة بالفعل.")

    row = UserFollowedSignal(user_id=user_id, decision_v2_snapshot_id=decision_v2_snapshot_id, symbol=snapshot.symbol)
    session.add(row)
    session.commit()
    return row


def unfollow_signal(session: Session, user_id: int, decision_v2_snapshot_id: int) -> None:
    row = (
        session.query(UserFollowedSignal)
        .filter_by(user_id=user_id, decision_v2_snapshot_id=decision_v2_snapshot_id)
        .first()
    )
    if row is None:
        raise SignalSnapshotNotFoundError("لا تتابع هذه الإشارة.")
    session.delete(row)
    session.commit()


def _to_record(followed: UserFollowedSignal, snapshot: DecisionV2Snapshot, outcome: Optional[DecisionV2Outcome]) -> FollowedSignalRecord:
    return FollowedSignalRecord(
        id=followed.id,
        decision_v2_snapshot_id=snapshot.id,
        symbol=snapshot.symbol,
        company_name_ar=snapshot.company_name_ar,
        followed_at=followed.followed_at,
        decision=snapshot.decision,
        decision_label_ar=snapshot.decision_label_ar,
        entry_zone_low=float(snapshot.entry_zone_low) if snapshot.entry_zone_low is not None else None,
        entry_zone_high=float(snapshot.entry_zone_high) if snapshot.entry_zone_high is not None else None,
        stop_loss=float(snapshot.stop_loss) if snapshot.stop_loss is not None else None,
        target_1=float(snapshot.target_1) if snapshot.target_1 is not None else None,
        target_2=float(snapshot.target_2) if snapshot.target_2 is not None else None,
        target_3=float(snapshot.target_3) if snapshot.target_3 is not None else None,
        outcome_status=outcome.status.value if outcome is not None else None,
        outcome_status_label_ar=OUTCOME_STATUS_LABEL_AR.get(outcome.status) if outcome is not None else None,
        outcome_return_pct=float(outcome.return_pct) if outcome is not None and outcome.return_pct is not None else None,
    )


def list_followed_signals(session: Session, user_id: int) -> List[FollowedSignalRecord]:
    rows = (
        session.query(UserFollowedSignal)
        .filter_by(user_id=user_id)
        .order_by(UserFollowedSignal.followed_at.desc())
        .all()
    )
    records = []
    for row in rows:
        snapshot = session.query(DecisionV2Snapshot).filter_by(id=row.decision_v2_snapshot_id).first()
        if snapshot is None:
            continue
        outcome = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).first()
        records.append(_to_record(row, snapshot, outcome))
    return records


def _win_rate(outcomes: List[DecisionV2Outcome]) -> tuple[int, Optional[float]]:
    target_hits = [o for o in outcomes if o.status in _TARGET_STATUSES]
    stop_hits = [o for o in outcomes if o.status == _STOP_STATUS]
    decisive = target_hits + stop_hits
    if not decisive:
        return 0, None
    return len(decisive), round(len(target_hits) / len(decisive) * 100, 2)


def compute_personal_vs_algorithm_performance(session: Session, user_id: int) -> PersonalPerformanceComparison:
    followed_snapshot_ids = [
        row[0]
        for row in session.query(UserFollowedSignal.decision_v2_snapshot_id).filter_by(user_id=user_id).all()
    ]
    personal_outcomes: List[DecisionV2Outcome] = (
        session.query(DecisionV2Outcome)
        .filter(DecisionV2Outcome.decision_v2_snapshot_id.in_(followed_snapshot_ids))
        .all()
        if followed_snapshot_ids
        else []
    )
    personal_sample_size, personal_win_rate = _win_rate(personal_outcomes)

    algorithm_outcomes: List[DecisionV2Outcome] = session.query(DecisionV2Outcome).all()
    algorithm_sample_size, algorithm_win_rate = _win_rate(algorithm_outcomes)

    insufficient_message = None
    if personal_sample_size == 0 and algorithm_sample_size == 0:
        insufficient_message = _INSUFFICIENT_DATA_AR

    return PersonalPerformanceComparison(
        generated_at=datetime.now(timezone.utc),
        personal_resolved_sample_size=personal_sample_size,
        personal_win_rate_pct=personal_win_rate,
        personal_small_sample_warning=personal_sample_size < MIN_RESOLVED_SAMPLE_SIZE,
        algorithm_resolved_sample_size=algorithm_sample_size,
        algorithm_win_rate_pct=algorithm_win_rate,
        algorithm_small_sample_warning=algorithm_sample_size < ALGORITHM_MIN_RESOLVED_SAMPLE_SIZE,
        insufficient_data_message_ar=insufficient_message,
    )
