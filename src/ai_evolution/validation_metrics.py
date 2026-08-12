"""M10 (Part G): rigorous, honest metrics over one `ValidationSession`'s
`DecisionV2Snapshot`/`DecisionV2Outcome` rows.

Every metric here is computed live from the session's own rows -- no
scheduled pre-aggregation table, unlike E9's `daily_intelligence_
aggregation.py`. A `ValidationSession` is a rare, deliberately opened
event (not a daily cron target), so a live query is the honest choice:
it can never show a stale number for an operator actively watching a
session in progress.

Central discipline, restated from the M10 mandate: `DATA_UNAVAILABLE`
is never counted as a win or a loss anywhere below (see
`_TARGET_STATUSES`/`_STOP_STATUS` -- `DATA_UNAVAILABLE` appears in
neither), and `PARTIAL` (a same-bar target/stop tie, genuinely
undecidable with daily OHLC) is excluded from win/loss and calibration
math for the same reason, not folded into either side to make the
denominator look bigger.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.ai_evolution.confidence_calibration import expected_calibration_error
from src.ai_evolution.decision_v2_outcome_evaluation import is_actionable_buy_decision
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot

_TARGET_STATUSES = (
    DecisionV2OutcomeStatus.TARGET_1_HIT,
    DecisionV2OutcomeStatus.TARGET_2_HIT,
    DecisionV2OutcomeStatus.TARGET_3_HIT,
)
_TARGET_STATUS_BY_NUMBER = {
    1: DecisionV2OutcomeStatus.TARGET_1_HIT,
    2: DecisionV2OutcomeStatus.TARGET_2_HIT,
    3: DecisionV2OutcomeStatus.TARGET_3_HIT,
}
_STOP_STATUS = DecisionV2OutcomeStatus.STOP_LOSS_HIT
_RETURN_BEARING_STATUSES = _TARGET_STATUSES + (_STOP_STATUS, DecisionV2OutcomeStatus.EXPIRED)


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


@dataclass(frozen=True)
class RankPerformance:
    rank: int
    signal_count: int
    win_rate: Optional[float]
    average_return_pct: Optional[float]


@dataclass(frozen=True)
class DuplicateSignal:
    symbol: str
    signal_count: int


@dataclass(frozen=True)
class ValidationSessionMetrics:
    validation_session_id: int

    total_signals_issued: int
    actionable_signals: int
    status_counts: Dict[str, int]

    win_rate: Optional[float]
    decisive_signal_count: int
    false_positive_rate: Optional[float]

    target_hit_rate_by_target: Dict[int, Optional[float]]
    stop_loss_rate: Optional[float]

    average_return_pct: Optional[float]
    expectancy_pct: Optional[float]

    average_time_to_target_days: Optional[float]
    average_time_to_stop_days: Optional[float]

    ranking_position_performance: List[RankPerformance]

    calibration_pair_count: int
    expected_calibration_error: Optional[float]

    duplicate_signals: List[DuplicateSignal]
    duplicate_signal_rate: Optional[float]

    data_unavailable_count: int
    data_unavailable_rate: Optional[float]

    pending_count: int
    cancelled_count: int
    partial_count: int


def _status_counts(outcomes: List[DecisionV2Outcome]) -> Dict[str, int]:
    counts: Dict[str, int] = {status.value: 0 for status in DecisionV2OutcomeStatus}
    for outcome in outcomes:
        counts[outcome.status.value] += 1
    return counts


def _target_hit_rate_by_target(outcomes: List[DecisionV2Outcome], actionable_total: int) -> Dict[int, Optional[float]]:
    if actionable_total == 0:
        return {1: None, 2: None, 3: None}
    return {
        number: sum(1 for o in outcomes if o.status == status) / actionable_total
        for number, status in _TARGET_STATUS_BY_NUMBER.items()
    }


def _ranking_position_performance(
    snapshot_by_id: Dict[int, DecisionV2Snapshot], outcomes: List[DecisionV2Outcome]
) -> List[RankPerformance]:
    by_rank: Dict[int, List[DecisionV2Outcome]] = defaultdict(list)
    for outcome in outcomes:
        snapshot = snapshot_by_id.get(outcome.decision_v2_snapshot_id)
        if snapshot is None or snapshot.ranking_position is None:
            continue
        by_rank[snapshot.ranking_position].append(outcome)

    results = []
    for rank in sorted(by_rank):
        rows = by_rank[rank]
        decisive = [o for o in rows if o.status in _TARGET_STATUSES or o.status == _STOP_STATUS]
        wins = [o for o in decisive if o.status in _TARGET_STATUSES]
        returns = [float(o.return_pct) for o in rows if o.return_pct is not None]
        results.append(
            RankPerformance(
                rank=rank,
                signal_count=len(rows),
                win_rate=(len(wins) / len(decisive)) if decisive else None,
                average_return_pct=_mean(returns),
            )
        )
    return results


def _calibration_pairs(
    snapshot_by_id: Dict[int, DecisionV2Snapshot], outcomes: List[DecisionV2Outcome]
) -> List[Tuple[float, int]]:
    pairs = []
    for outcome in outcomes:
        if outcome.status not in _TARGET_STATUSES and outcome.status != _STOP_STATUS:
            continue
        snapshot = snapshot_by_id.get(outcome.decision_v2_snapshot_id)
        if snapshot is None or snapshot.confidence_score is None:
            continue
        label = 1 if outcome.status in _TARGET_STATUSES else 0
        pairs.append((float(snapshot.confidence_score), label))
    return pairs


def _duplicate_signals(snapshots: List[DecisionV2Snapshot]) -> List[DuplicateSignal]:
    by_symbol: Dict[str, int] = defaultdict(int)
    for snapshot in snapshots:
        by_symbol[snapshot.symbol] += 1
    duplicates = [
        DuplicateSignal(symbol=symbol, signal_count=count) for symbol, count in by_symbol.items() if count > 1
    ]
    duplicates.sort(key=lambda d: (-d.signal_count, d.symbol))
    return duplicates


def compute_validation_session_metrics(session: Session, validation_session_id: int) -> ValidationSessionMetrics:
    """Pure query + aggregation -- never writes to the DB, safe to call
    as often as an operator refreshes the dashboard."""
    snapshots = (
        session.query(DecisionV2Snapshot)
        .filter(DecisionV2Snapshot.validation_session_id == validation_session_id)
        .all()
    )
    snapshot_by_id = {s.id: s for s in snapshots}

    outcomes = (
        session.query(DecisionV2Outcome)
        .filter(DecisionV2Outcome.validation_session_id == validation_session_id)
        .all()
    )

    total_signals_issued = len(snapshots)
    actionable_signals = sum(1 for s in snapshots if is_actionable_buy_decision(s.decision))

    status_counts = _status_counts(outcomes)

    target_hits = [o for o in outcomes if o.status in _TARGET_STATUSES]
    stop_hits = [o for o in outcomes if o.status == _STOP_STATUS]
    decisive = target_hits + stop_hits
    win_rate = (len(target_hits) / len(decisive)) if decisive else None

    expired = [o for o in outcomes if o.status == DecisionV2OutcomeStatus.EXPIRED]
    expired_negative = [o for o in expired if o.return_pct is not None and float(o.return_pct) < 0]
    false_positive_denominator = len(target_hits) + len(stop_hits) + len(expired)
    false_positive_rate = (
        (len(stop_hits) + len(expired_negative)) / false_positive_denominator
        if false_positive_denominator > 0
        else None
    )

    all_returns = [float(o.return_pct) for o in outcomes if o.status in _RETURN_BEARING_STATUSES and o.return_pct is not None]
    decisive_returns = [float(o.return_pct) for o in decisive if o.return_pct is not None]

    target_hit_days = [o.time_to_target_days for o in target_hits if o.time_to_target_days is not None]
    stop_hit_days = [o.time_to_stop_days for o in stop_hits if o.time_to_stop_days is not None]

    calibration_pairs = _calibration_pairs(snapshot_by_id, outcomes)

    duplicate_signals = _duplicate_signals(snapshots)
    duplicate_signal_rate = (
        sum(d.signal_count for d in duplicate_signals) / total_signals_issued if total_signals_issued > 0 else None
    )

    data_unavailable_count = status_counts[DecisionV2OutcomeStatus.DATA_UNAVAILABLE.value]

    return ValidationSessionMetrics(
        validation_session_id=validation_session_id,
        total_signals_issued=total_signals_issued,
        actionable_signals=actionable_signals,
        status_counts=status_counts,
        win_rate=win_rate,
        decisive_signal_count=len(decisive),
        false_positive_rate=false_positive_rate,
        target_hit_rate_by_target=_target_hit_rate_by_target(outcomes, actionable_signals),
        stop_loss_rate=(len(stop_hits) / actionable_signals) if actionable_signals > 0 else None,
        average_return_pct=_mean(all_returns),
        expectancy_pct=_mean(decisive_returns),
        average_time_to_target_days=_mean([float(d) for d in target_hit_days]),
        average_time_to_stop_days=_mean([float(d) for d in stop_hit_days]),
        ranking_position_performance=_ranking_position_performance(snapshot_by_id, outcomes),
        calibration_pair_count=len(calibration_pairs),
        expected_calibration_error=expected_calibration_error(calibration_pairs),
        duplicate_signals=duplicate_signals,
        duplicate_signal_rate=duplicate_signal_rate,
        data_unavailable_count=data_unavailable_count,
        data_unavailable_rate=(data_unavailable_count / actionable_signals) if actionable_signals > 0 else None,
        pending_count=status_counts[DecisionV2OutcomeStatus.PENDING.value],
        cancelled_count=status_counts[DecisionV2OutcomeStatus.CANCELLED.value],
        partial_count=status_counts[DecisionV2OutcomeStatus.PARTIAL.value],
    )
