"""Baseline-V2 vs Phase-3-V2 strategy pair for the DecisionEngineV2
historical validation harness.

Deliberately NOT "V1 vs V2" -- both arms run the real `DecisionEngineV2`
orchestrator (`.decide()`), one from the frozen pre-Phase-3 snapshot
(`src.backtesting.decision_v2_baseline`), one from the live, current
package (`src.analysis.decision_v2`). The upstream V1 `AIDecisionEngine`
step both wrap is unchanged by Phase 3 (confirmed: `git diff fa2acfe
HEAD -- src/analysis/decision/` shows only docstring-only diffs in
`technical_contributor.py`/`external_factor_contributors.py`) --
computed exactly once per (symbol, date) and fed identically to both
arms, so nothing about the comparison depends on re-deriving it twice.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from src.ai_evolution.confidence_calibration import TRAINING_SOURCE_DECISION_V2, get_effective_confidence
from src.analysis.decision.ai_decision_engine import AIDecisionEngine
from src.analysis.decision.types import InvestmentDecision
from src.analysis.decision_v2.engine import DecisionEngineV2 as Phase3DecisionEngineV2
from src.backtesting.data_access import DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS
from src.backtesting.decision_v2_baseline.engine import DecisionEngineV2 as BaselineDecisionEngineV2
from src.backtesting.decision_v2_context import DecisionV2AsOfContext, build_decision_v2_as_of_context
from src.domain.models import Stock

BASELINE_VARIANT = "baseline_v2"
PHASE3_VARIANT = "phase3_v2"


@dataclass(frozen=True)
class DecisionV2ReplayPoint:
    """One (symbol, evaluation date) point, built once and shared by
    both engine variants -- the structural guarantee behind "identical
    sample comparison" (item 8): there is exactly one object each arm
    reads, not two independently-constructed ones that could drift."""

    stock: Stock
    as_of: date
    as_of_context: DecisionV2AsOfContext
    investment_decision: InvestmentDecision


def build_replay_point(
    session: Session,
    stock: Stock,
    as_of: date,
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
) -> Optional[DecisionV2ReplayPoint]:
    """`None` when there is not enough as-of-safe data to evaluate this
    point at all -- recorded by the harness as a skipped evaluation,
    the same "insufficient_data" bucket src.backtesting.engine already
    uses, never a forced HOLD/no-signal outcome."""
    as_of_context = build_decision_v2_as_of_context(session, stock, as_of, fundamental_reporting_lag_days)
    if not as_of_context.has_any_input:
        return None
    investment_decision = AIDecisionEngine().decide(as_of_context.context)
    return DecisionV2ReplayPoint(
        stock=stock, as_of=as_of, as_of_context=as_of_context, investment_decision=investment_decision
    )


def _decide_kwargs(point: DecisionV2ReplayPoint) -> dict:
    ctx = point.as_of_context
    return dict(
        company_name_ar=ctx.company_name_ar,
        company_name_en=ctx.company_name_en,
        sector=ctx.sector,
        sector_ar=ctx.sector_ar,
        is_synthetic=ctx.is_synthetic,
        data_source=ctx.data_source,
        quote_timestamp=ctx.quote_timestamp,
        market_status=ctx.market_status,
        market_is_open=ctx.market_is_open,
        scan_run_id=None,
        market_breadth=ctx.market_breadth,
        evaluation_time=ctx.evaluation_time,
    )


def run_baseline_v2(point: DecisionV2ReplayPoint):
    """Runs the frozen pre-Phase-3 DecisionEngineV2 -- see
    src.backtesting.decision_v2_baseline's provenance note. Never
    receives confidence calibration (Phase 3 area 2 structural repair,
    see `run_phase3_v2` below) -- that mechanism postdates this frozen
    snapshot entirely, the same reason it never received the anti-
    chase/breakout-confirmation/sector-strength repairs either."""
    return BaselineDecisionEngineV2().decide(
        point.as_of_context.context, point.investment_decision, **_decide_kwargs(point)
    )


def run_phase3_v2(point: DecisionV2ReplayPoint, session: Optional[Session] = None):
    """Runs the live, current DecisionEngineV2 -- the exact same
    class/module production imports.

    `session` (Phase 3 area 2 structural repair, optional -- `None`,
    the default and every caller before this repair, preserves the
    exact single-pass behavior this always had): when provided, applies
    the existing, already-trained-and-activated ConfidenceCalibration
    Engine model (if any) to this point's own raw confidence via a
    second `decide()` call -- the same two-step "compute raw, then
    calibrate, then let the SECOND pass's gates see the calibrated
    value" pattern real live production would need to actually exercise
    `gates.py`'s `confidence_calibration_applied` gate (that engine
    never queries the database itself -- see `DecisionEngineV2.decide()`'s
    own docstring for `calibrated_success_probability`). Never trains
    or activates a calibrator itself -- `get_effective_confidence` only
    ever reads whichever model is already ACTIVE through the separate,
    human-gated `ConfidenceCalibrationEngine` lifecycle; in a fresh
    backtest run with no such model yet, this correctly falls back to
    the single-pass result unchanged (the honest "not enough history"
    state, not a defect)."""
    kwargs = _decide_kwargs(point)
    result = Phase3DecisionEngineV2().decide(point.as_of_context.context, point.investment_decision, **kwargs)
    if session is None:
        return result
    calibrated_probability, _version = get_effective_confidence(
        session, result.confidence_score, source=TRAINING_SOURCE_DECISION_V2
    )
    if calibrated_probability is None:
        return result
    return Phase3DecisionEngineV2().decide(
        point.as_of_context.context, point.investment_decision,
        **{**kwargs, "calibrated_success_probability": calibrated_probability},
    )
