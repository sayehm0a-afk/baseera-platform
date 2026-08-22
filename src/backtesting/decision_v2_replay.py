"""DecisionEngineV2 historical replay runner -- the orchestrator that
ties `decision_v2_strategies.py` (Baseline V2 vs Phase 3 V2),
`decision_v2_backtest_outcome.py` (outcome evaluation), and a
V2-shaped result record together into one Baseline-vs-Phase-3
comparison run.

`DecisionV2BacktestRecord` is deliberately an in-memory dataclass, not
a persisted DB table + migration: there is currently no real
historical Saudi-market dataset reachable from this environment to
populate one with (see the harness's own final report), so adding
schema churn for a table that would hold zero real rows was rejected
as premature. Every field item 5 of the mandate lists is present on
this dataclass; persisting it later is a mechanical `Base`+migration
addition once real data access exists, not a redesign.
"""

from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.analysis.decision_v2.types import DecisionResult
from src.backtesting.data_access import DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS, evaluation_dates
from src.backtesting.decision_v2_backtest_outcome import (
    DecisionV2BacktestOutcome,
    evaluate_decision_v2_backtest_outcome,
)
from src.backtesting.decision_v2_strategies import (
    BASELINE_VARIANT,
    PHASE3_VARIANT,
    build_replay_point,
    run_baseline_v2,
    run_phase3_v2,
)
from src.domain.models import Stock

DEFAULT_ENTRY_EXPIRY_DAYS = 10
DEFAULT_RESOLUTION_HORIZON_DAYS = 60


@dataclass(frozen=True)
class DecisionV2BacktestRecord:
    """One (symbol, evaluation date, variant) result -- the fields item
    5 of the mandate lists, plus the outcome fields item 6 lists."""

    variant: str  # "baseline_v2" or "phase3_v2"
    symbol: str
    evaluated_at: date
    decision: str
    confidence_score: float
    opportunity_quality_score: Optional[float]
    risk_score: Optional[float]
    entry_zone_low: Optional[float]
    entry_zone_high: Optional[float]
    entry_status: str
    stop_loss: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    target_3: Optional[float]
    risk_reward_target_1: Optional[float]
    market_risk_state: str
    sector: Optional[str]
    sector_strength_used: bool
    stock_vs_sector_relative_strength: Optional[float]
    breakout_status: str
    is_high_quality_buy: bool
    data_freshness_status: str
    data_source: str
    engine_version: str
    unavailable_features: tuple
    outcome: DecisionV2BacktestOutcome


def _to_record(variant: str, symbol: str, as_of: date, decision: DecisionResult, unavailable_features: tuple, outcome: DecisionV2BacktestOutcome) -> DecisionV2BacktestRecord:
    return DecisionV2BacktestRecord(
        variant=variant,
        symbol=symbol,
        evaluated_at=as_of,
        decision=decision.decision.value,
        confidence_score=decision.confidence_score,
        opportunity_quality_score=decision.opportunity_quality_score,
        risk_score=decision.risk_score,
        entry_zone_low=decision.entry_zone_low,
        entry_zone_high=decision.entry_zone_high,
        entry_status=decision.entry_status.value,
        stop_loss=decision.stop_loss,
        target_1=decision.target_1,
        target_2=decision.target_2,
        target_3=decision.target_3,
        risk_reward_target_1=decision.risk_reward_target_1,
        market_risk_state=decision.market_risk_state,
        sector=getattr(decision, "sector_name", None),
        sector_strength_used=getattr(decision, "sector_strength_used", False),
        stock_vs_sector_relative_strength=getattr(decision, "stock_vs_sector_relative_strength", None),
        breakout_status=getattr(decision, "breakout_status", "NOT_APPLICABLE"),
        is_high_quality_buy=getattr(decision, "is_high_quality_buy", False),
        data_freshness_status=decision.data_freshness_status.value,
        data_source=decision.data_source,
        engine_version=decision.analysis_version,
        unavailable_features=unavailable_features,
        outcome=outcome,
    )


@dataclass(frozen=True)
class DecisionV2ReplaySummary:
    baseline_records: List[DecisionV2BacktestRecord]
    phase3_records: List[DecisionV2BacktestRecord]
    skipped: dict  # {"symbol_not_found": int, "insufficient_data": int}
    evaluated_points: int


def run_decision_v2_replay(
    session: Session,
    symbols: List[str],
    start_date: date,
    end_date: date,
    evaluation_frequency_days: int = 7,
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    entry_expiry_days: int = DEFAULT_ENTRY_EXPIRY_DAYS,
    resolution_horizon_days: int = DEFAULT_RESOLUTION_HORIZON_DAYS,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> DecisionV2ReplaySummary:
    """The single run loop both arms share -- one (symbol, date) grid,
    one `build_replay_point()` call per point (item 8's "identical
    sample" guarantee), both engine variants evaluated against it, both
    outcomes evaluated with the identical as-of-safe forward window. A
    symbol/date this harness cannot evaluate at all (no as-of-safe
    input) is recorded as skipped -- for BOTH arms identically -- never
    silently dropped from just one side."""
    dates = evaluation_dates(start_date, end_date, evaluation_frequency_days)
    baseline_records: List[DecisionV2BacktestRecord] = []
    phase3_records: List[DecisionV2BacktestRecord] = []
    skipped = {"symbol_not_found": 0, "insufficient_data": 0}
    evaluated_points = 0

    for symbol in symbols:
        if is_cancelled and is_cancelled():
            break
        stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
        if stock is None:
            skipped["symbol_not_found"] += len(dates)
            continue

        for as_of in dates:
            if is_cancelled and is_cancelled():
                break
            point = build_replay_point(session, stock, as_of, fundamental_reporting_lag_days)
            if point is None:
                skipped["insufficient_data"] += 1
                continue

            baseline_decision = run_baseline_v2(point)
            phase3_decision = run_phase3_v2(point)

            baseline_outcome = evaluate_decision_v2_backtest_outcome(
                session, stock, baseline_decision, as_of, entry_expiry_days, resolution_horizon_days
            )
            phase3_outcome = evaluate_decision_v2_backtest_outcome(
                session, stock, phase3_decision, as_of, entry_expiry_days, resolution_horizon_days
            )

            unavailable = point.as_of_context.unavailable_features
            baseline_records.append(_to_record(BASELINE_VARIANT, symbol, as_of, baseline_decision, unavailable, baseline_outcome))
            phase3_records.append(_to_record(PHASE3_VARIANT, symbol, as_of, phase3_decision, unavailable, phase3_outcome))
            evaluated_points += 1

    return DecisionV2ReplaySummary(
        baseline_records=baseline_records, phase3_records=phase3_records, skipped=skipped,
        evaluated_points=evaluated_points,
    )
