"""OWNER-only performance dashboard for Basirah's personal day-trading
product -- CONT Phase 3. Reads exactly two real, already-persisted
sources, computes nothing that wasn't already stored, and fabricates
nothing when a sample is too small to mean anything:

1. `DecisionV2Snapshot` (scan-originated rows only, `scan_run_id IS NOT
   NULL`) for what Basirah actually *told* the user -- decision/entry-
   status/market-risk-state/sector distributions. This is the exact
   table `personal_scan.select_top_opportunities()` reads, so these
   distributions describe the real "امسح السوق الآن" product surface,
   not a different, older recommendation pipeline.
2. `RecommendationSnapshot` + `RecommendationOutcome` (source="live_scan",
   is_paper_trade=False) for what actually *happened* -- target/stop
   hit rates, MFE/MAE, realized return, and confidence calibration.
   These are written by the same live-scan write path (see
   `MarketIntelligenceRepository.save_symbol_records`) at the same
   `evaluated_at`/`decision_timestamp`, so they describe outcomes for
   the same population of live decisions, just via the older,
   backtest-compatible schema that already carries per-horizon outcome
   tracking (E1/E2, Phase-1-hardening #298-300).

`market_risk_state` is a Decision-V2-only field with no equivalent
column on `RecommendationOutcome` -- there is no real data to compute a
calibration-by-market-risk-state breakdown from, so that field is
always `None` with `market_risk_state_calibration_unavailable_ar` set,
never a fabricated or misleadingly-empty breakdown.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.ai_evolution.outcome_evaluation import EVALUATION_HORIZON_DAYS
from src.backtesting.metrics import EvaluationOutcome, breakdown_by, calibration_error
from src.domain.models import (
    DecisionV2Snapshot,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)

_MARKET_RISK_STATE_UNAVAILABLE_AR = (
    "بيانات غير كافية -- لا يوجد ربط بين حالة مخاطر السوق وتتبع نتائج التوصيات حالياً"
)
_INSUFFICIENT_DATA_AR = "بيانات غير كافية لعرض هذا المقياس"

# A group's win_rate/calibration is only reported as a "strongest" or
# "weakest" group once at least this many terminal outcomes back it --
# matches RecommendationHistoryStatsOut's own small_sample_warning
# threshold (30) for the same "never let one lucky/unlucky call look
# like a track record" reason.
_MIN_GROUP_SAMPLE_SIZE = 10

_TERMINAL_STATUSES = {
    RecommendationOutcomeStatus.SUCCESSFUL,
    RecommendationOutcomeStatus.FAILED,
    RecommendationOutcomeStatus.PARTIAL,
}


@dataclass(frozen=True)
class GroupPerformance:
    group: str
    sample_size: int
    win_rate: Optional[float]


@dataclass(frozen=True)
class PersonalPerformanceDashboard:
    generated_at: datetime
    evaluation_horizon_days: int

    total_decisions_issued: int
    decision_distribution: Dict[str, int]
    entry_status_distribution: Dict[str, int]
    market_risk_state_distribution: Dict[str, int]
    sector_distribution: Dict[str, int]

    outcome_sample_size: int
    terminal_outcome_sample_size: int
    status_counts: Dict[str, int]
    target_1_hit_rate: Optional[float]
    target_2_hit_rate: Optional[float]
    target_3_hit_rate: Optional[float]
    stop_loss_hit_rate: Optional[float]
    expired_count: int
    unresolved_count: int
    average_max_favorable_excursion_pct: Optional[float]
    average_max_adverse_excursion_pct: Optional[float]
    average_realized_return_pct: Optional[float]
    # Real elapsed days from issuance to the first target actually
    # touched (RecommendationOutcome.time_to_target_days, populated by
    # outcome_evaluation.py's own price-path replay) -- lets the owner
    # compare Basirah's stated time_horizon against what actually
    # happened, instead of only ever seeing the *expected* duration.
    # None across outcomes where no target was ever reached, not 0.
    average_time_to_target_days: Optional[float]

    calibration_by_bucket: Optional[Dict]
    calibration_by_type: Dict[str, Dict]
    calibration_by_holding_period: Dict[str, Dict]
    calibration_by_sector: Dict[str, Dict]
    market_risk_state_calibration_unavailable_ar: str

    strongest_groups: List[GroupPerformance]
    weakest_groups: List[GroupPerformance]

    small_sample_warning: bool
    insufficient_data_message_ar: Optional[str]


def _decision_distribution(session: Session) -> Dict[str, int]:
    rows = (
        session.query(DecisionV2Snapshot.decision, func.count(DecisionV2Snapshot.id))
        .filter(DecisionV2Snapshot.scan_run_id.isnot(None))
        .group_by(DecisionV2Snapshot.decision)
        .all()
    )
    return {decision: count for decision, count in rows}


def _string_column_distribution(session: Session, column) -> Dict[str, int]:
    rows = (
        session.query(column, func.count(DecisionV2Snapshot.id))
        .filter(DecisionV2Snapshot.scan_run_id.isnot(None))
        .filter(column.isnot(None))
        .group_by(column)
        .all()
    )
    return {value: count for value, count in rows}


def _average(values: List[Optional[float]]) -> Optional[float]:
    known = [float(v) for v in values if v is not None]
    if not known:
        return None
    return round(sum(known) / len(known), 4)


def _fraction(numerator_flags: List[Optional[bool]]) -> Optional[float]:
    known = [flag for flag in numerator_flags if flag is not None]
    if not known:
        return None
    return round(sum(1 for flag in known if flag) / len(known) * 100, 2)


def _fetch_live_outcomes(session: Session, evaluation_horizon_days: int):
    return (
        session.query(RecommendationOutcome, RecommendationSnapshot, Stock)
        .join(RecommendationSnapshot, RecommendationOutcome.snapshot_id == RecommendationSnapshot.id)
        .outerjoin(Stock, RecommendationSnapshot.stock_id == Stock.id)
        .filter(RecommendationOutcome.evaluation_horizon_days == evaluation_horizon_days)
        .filter(RecommendationSnapshot.source == "live_scan")
        .filter(RecommendationSnapshot.is_paper_trade.is_(False))
        .all()
    )


def _to_evaluation_outcome(outcome: RecommendationOutcome, snapshot: RecommendationSnapshot, stock: Optional[Stock]) -> EvaluationOutcome:
    return EvaluationOutcome(
        symbol=snapshot.symbol,
        evaluated_at=snapshot.evaluated_at.date(),
        recommendation=snapshot.recommendation.value,
        confidence=float(snapshot.confidence_score),
        total_score=float(snapshot.total_score),
        risk_level=snapshot.risk_level,
        time_horizon=snapshot.time_horizon,
        sector=stock.sector if stock is not None else None,
        market_price_at_evaluation=(
            float(snapshot.market_price_at_evaluation) if snapshot.market_price_at_evaluation is not None else None
        ),
        target_price=float(snapshot.target_price) if snapshot.target_price is not None else None,
        stop_loss=float(snapshot.stop_loss) if snapshot.stop_loss is not None else None,
        forward_return_pct=float(outcome.return_pct) if outcome.return_pct is not None else None,
        hit_target=outcome.hit_target,
        hit_stop_loss=outcome.hit_stop,
        position_size=snapshot.position_size,
    )


def _rank_groups(breakdown: Dict[str, Dict]) -> List[GroupPerformance]:
    eligible = [
        GroupPerformance(group=key, sample_size=metrics["evaluation_count"], win_rate=metrics["win_rate"])
        for key, metrics in breakdown.items()
        if metrics["evaluation_count"] >= _MIN_GROUP_SAMPLE_SIZE and metrics["win_rate"] is not None
    ]
    return sorted(eligible, key=lambda g: g.win_rate, reverse=True)


def compute_personal_performance_dashboard(
    session: Session, evaluation_horizon_days: int = 7
) -> PersonalPerformanceDashboard:
    if evaluation_horizon_days not in EVALUATION_HORIZON_DAYS:
        evaluation_horizon_days = 7

    total_decisions_issued = (
        session.query(func.count(DecisionV2Snapshot.id)).filter(DecisionV2Snapshot.scan_run_id.isnot(None)).scalar()
        or 0
    )
    decision_distribution = _decision_distribution(session)
    entry_status_distribution = _string_column_distribution(session, DecisionV2Snapshot.entry_status)
    market_risk_state_distribution = _string_column_distribution(session, DecisionV2Snapshot.market_risk_state)
    sector_distribution = _string_column_distribution(session, DecisionV2Snapshot.sector_ar)

    rows = _fetch_live_outcomes(session, evaluation_horizon_days)
    outcome_sample_size = len(rows)
    outcomes_only = [row[0] for row in rows]
    terminal_rows = [row for row in rows if row[0].status in _TERMINAL_STATUSES]
    terminal_outcome_sample_size = len(terminal_rows)

    status_counts: Dict[str, int] = {}
    for outcome in outcomes_only:
        status_counts[outcome.status.value] = status_counts.get(outcome.status.value, 0) + 1

    evaluation_outcomes = [_to_evaluation_outcome(o, s, stock) for o, s, stock in terminal_rows]

    calibration = calibration_error(evaluation_outcomes) if evaluation_outcomes else None
    by_type = breakdown_by(evaluation_outcomes, lambda o: o.recommendation) if evaluation_outcomes else {}
    by_holding_period = breakdown_by(evaluation_outcomes, lambda o: o.time_horizon) if evaluation_outcomes else {}
    by_sector = breakdown_by(evaluation_outcomes, lambda o: o.sector) if evaluation_outcomes else {}

    strongest = _rank_groups(by_sector)
    weakest = list(reversed(strongest))

    small_sample = terminal_outcome_sample_size < _MIN_GROUP_SAMPLE_SIZE
    insufficient_message = _INSUFFICIENT_DATA_AR if outcome_sample_size == 0 else None

    return PersonalPerformanceDashboard(
        generated_at=datetime.now(timezone.utc),
        evaluation_horizon_days=evaluation_horizon_days,
        total_decisions_issued=total_decisions_issued,
        decision_distribution=decision_distribution,
        entry_status_distribution=entry_status_distribution,
        market_risk_state_distribution=market_risk_state_distribution,
        sector_distribution=sector_distribution,
        outcome_sample_size=outcome_sample_size,
        terminal_outcome_sample_size=terminal_outcome_sample_size,
        status_counts=status_counts,
        target_1_hit_rate=_fraction([o.target_1_reached for o in outcomes_only]),
        target_2_hit_rate=_fraction([o.target_2_reached for o in outcomes_only]),
        target_3_hit_rate=_fraction([o.target_3_reached for o in outcomes_only]),
        stop_loss_hit_rate=_fraction([o.hit_stop for o in outcomes_only]),
        expired_count=status_counts.get(RecommendationOutcomeStatus.EXPIRED.value, 0),
        unresolved_count=status_counts.get(RecommendationOutcomeStatus.PENDING.value, 0),
        average_max_favorable_excursion_pct=_average([o.max_favorable_excursion_pct for o in outcomes_only]),
        average_max_adverse_excursion_pct=_average([o.max_adverse_excursion_pct for o in outcomes_only]),
        average_realized_return_pct=_average([o.return_pct for o in outcomes_only]),
        average_time_to_target_days=_average([o.time_to_target_days for o in outcomes_only]),
        calibration_by_bucket=calibration,
        calibration_by_type=by_type,
        calibration_by_holding_period=by_holding_period,
        calibration_by_sector=by_sector,
        market_risk_state_calibration_unavailable_ar=_MARKET_RISK_STATE_UNAVAILABLE_AR,
        strongest_groups=strongest[:3],
        weakest_groups=weakest[:3],
        small_sample_warning=small_sample,
        insufficient_data_message_ar=insufficient_message,
    )
