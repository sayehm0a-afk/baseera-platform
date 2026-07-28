"""E4 (part 2 of 2) of the AI Evolution Layer: splits live outcome
accuracy by whether a recommendation involved the (not-yet-built,
see E7) real multi-agent debate panel -- `RecommendationSnapshot
.agent_debate_summary` is non-null only when a debate actually ran.

Lives here rather than in `src.backtesting.metrics` because it reads
live DB models (`RecommendationSnapshot`/`RecommendationOutcome`)
directly, not the backtest-only `EvaluationOutcome` dataclass those
functions operate on -- `agent_debate_summary` has no backtest
equivalent (BacktestingEngine never runs an agent panel).

Until E7 lands, every live snapshot's `agent_debate_summary` is null,
so the "llm_assisted" group will always be empty here -- an honest
reflection of the current system, not a bug to work around.
"""

from datetime import date
from statistics import mean
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.domain.models import RecommendationOutcome, RecommendationOutcomeStatus, RecommendationSnapshot

_TERMINAL_STATUSES = (RecommendationOutcomeStatus.SUCCESSFUL, RecommendationOutcomeStatus.FAILED)


def _group_metrics(rows) -> Dict:
    count = len(rows)
    if count == 0:
        return {"count": 0, "win_rate": None, "average_confidence": None, "average_return_pct": None}

    successes = sum(1 for _, outcome in rows if outcome.status is RecommendationOutcomeStatus.SUCCESSFUL)
    confidences = [float(snapshot.confidence_score) for snapshot, _ in rows]
    returns = [float(outcome.return_pct) for _, outcome in rows if outcome.return_pct is not None]

    return {
        "count": count,
        "win_rate": successes / count,
        "average_confidence": mean(confidences),
        "average_return_pct": mean(returns) if returns else None,
    }


def by_llm_reasoning_involvement(
    session: Session,
    evaluation_horizon_days: int,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> Dict[str, Dict]:
    """Compares accuracy between recommendations whose evidence
    included a real agent debate (`agent_debate_summary` non-null) and
    those that didn't, at one fixed evaluation horizon (see
    `src.ai_evolution.confidence_calibration`'s identical
    reference-horizon reasoning -- mixing horizons together would
    conflate different definitions of "outcome")."""
    query = (
        session.query(RecommendationSnapshot, RecommendationOutcome)
        .join(RecommendationOutcome, RecommendationOutcome.snapshot_id == RecommendationSnapshot.id)
        .filter(
            RecommendationOutcome.evaluation_horizon_days == evaluation_horizon_days,
            RecommendationOutcome.status.in_(_TERMINAL_STATUSES),
        )
    )
    if period_start is not None:
        query = query.filter(RecommendationSnapshot.evaluated_at >= period_start)
    if period_end is not None:
        query = query.filter(RecommendationSnapshot.evaluated_at <= period_end)

    rows = query.all()
    llm_assisted = [(s, o) for s, o in rows if s.agent_debate_summary is not None]
    technical_only = [(s, o) for s, o in rows if s.agent_debate_summary is None]

    return {
        "llm_assisted": _group_metrics(llm_assisted),
        "technical_only": _group_metrics(technical_only),
    }
