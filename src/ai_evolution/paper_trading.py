"""E8 of the AI Evolution Layer: champion/challenger paper trading and
the two-sample significance test that decides whether a challenger is
even shown to a human as activation-worthy.

Maps onto the design's Stage 2 (paper trade) of the observe -> paper-
trade -> human-gated-deploy pipeline. A "challenger" is always the most
recently VALIDATED-but-not-yet-ACTIVE `CalibrationConfig` -- a
candidate that has already passed `CalibrationEngine`'s own
validation-period backtest and is now waiting on a human activation
decision (`CalibrationEngine.activate()`, unchanged, still the only
code path that can promote a config to ACTIVE). Paper trading never
constructs its own config and never calls `activate()` itself.

`generate_challenger_snapshot()` re-scores the SAME already-built,
frozen `AnalysisContext` a live scan already computed for the champion
decision (no second data fetch) through a second `AIDecisionEngine`
built from the challenger config's JSON overrides -- reusing
`src.backtesting.calibration.parameters.build_strategy_kwargs`, the
exact JSON-config-to-engine-construction logic
`AIDecisionEngineStrategy` already uses for backtests. The result is
persisted as a second `RecommendationSnapshot` (`variant="challenger"`,
`is_paper_trade=True`) with its own PENDING `RecommendationOutcome`
rows via `create_pending_outcomes` -- zero duplicated evaluation logic;
a challenger's outcomes are scored by the exact same
`OutcomeEvaluationScheduler` that scores champion outcomes.

`two_sample_significance_test()` generalizes E5's one-sample proportion
z-test (`pattern_discovery.proportion_significance_test`, itself a
generalization of `statistical_calibration`'s one-sample z-test) to a
genuine two-sample, pooled-variance proportion z-test comparing
champion vs. challenger win rates. Deliberately one-sided (tests
whether the challenger's rate exceeds the champion's, not merely
differs from it): Part 9/10 of the design requires the challenger show
a significant *improvement* before a human is even shown the option to
activate it, not just a significant difference in either direction.

Never applied automatically -- `compare_champion_vs_challenger()` only
ever returns a result for a human to read; no code path in this module
calls `CalibrationEngine.activate()`.
"""

import logging
import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.ai_evolution.outcome_evaluation import create_pending_outcomes
from src.analysis.decision.ai_decision_engine import CATEGORY_LABELS, AIDecisionEngine, default_contributors
from src.analysis.decision.types import DecisionFactorBreakdown, InvestmentDecision
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.types import AnalysisContext, Signal
from src.backtesting.calibration.parameters import build_strategy_kwargs
from src.domain.models import (
    CalibrationConfig,
    CalibrationStatus,
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_SAMPLE_SIZE = 30
DEFAULT_SIGNIFICANCE_LEVEL = 0.05
DEFAULT_EVALUATION_HORIZON_DAYS = 7

CHAMPION_VARIANT = "champion"
CHALLENGER_VARIANT = "challenger"

_TERMINAL_STATUSES = (RecommendationOutcomeStatus.SUCCESSFUL, RecommendationOutcomeStatus.FAILED)


def _f(value: Optional[float]) -> Optional[float]:
    return None if value is None else float(value)


# Duplicated (not imported) from `MarketIntelligenceRepository`'s
# module-private `_serialize_signals`/`_serialize_breakdown` -- this
# module is imported BY that repository (see its E8 call site), so
# importing the other direction would create a cycle. This is the same
# ~10-line, non-diverging duplication `outcome_evaluation._hit_target_and_stop`
# already accepts for an identical reason.
def _serialize_signals(signals: List[Signal]) -> List[dict]:
    return [
        {
            "name": signal.name,
            "description": signal.description,
            "direction": signal.direction.value,
            "source": signal.source,
            "impact": signal.impact,
        }
        for signal in signals
    ]


def _serialize_breakdown(breakdown: List[DecisionFactorBreakdown]) -> List[dict]:
    return [
        {
            "category": item.category,
            "points": item.points,
            "weight": item.weight,
            "confidence": item.confidence,
            "available": item.available,
            "notes": item.notes,
        }
        for item in breakdown
    ]


def _category_score(decision: InvestmentDecision, category: str) -> Optional[float]:
    for item in decision.breakdown:
        if item.category == category and item.available:
            return round(item.points + 50.0, 2)
    return None


def get_latest_challenger_config(session: Session) -> Optional[CalibrationConfig]:
    """DRAFT candidates (not yet validated) and REJECTED/SUPERSEDED/
    ROLLED_BACK ones are never paper-traded against live traffic --
    only a config that has already cleared `CalibrationEngine`'s own
    validation-period backtest is eligible."""
    return (
        session.query(CalibrationConfig)
        .filter(CalibrationConfig.status == CalibrationStatus.VALIDATED)
        .order_by(CalibrationConfig.created_at.desc())
        .first()
    )


def build_challenger_engine(config: Dict) -> AIDecisionEngine:
    kwargs = build_strategy_kwargs(config, name="challenger")
    contributors = kwargs["contributors"] if kwargs["contributors"] is not None else default_contributors()
    recommendation_engine = RecommendationEngine(contributors=contributors, tuning=kwargs["recommendation_tuning"])
    return AIDecisionEngine(recommendation_engine=recommendation_engine, tuning=kwargs["ai_tuning"])


def generate_challenger_snapshot(
    session: Session,
    champion_snapshot: RecommendationSnapshot,
    context: AnalysisContext,
    challenger_config: CalibrationConfig,
) -> Optional[RecommendationSnapshot]:
    """Never raises: a challenger-generation bug must never take down
    champion scan persistence, the same discipline
    `AgentPanelOrchestrator.run_panel` already applies to E7's agent
    panel for an identical reason. Returns `None` (and logs) on any
    failure instead of propagating."""
    try:
        engine = build_challenger_engine(challenger_config.config)
        decision = engine.decide(context)

        challenger_snapshot = RecommendationSnapshot(
            run_id=None,
            stock_id=champion_snapshot.stock_id,
            symbol=champion_snapshot.symbol,
            evaluated_at=champion_snapshot.evaluated_at,
            market_price_at_evaluation=champion_snapshot.market_price_at_evaluation,
            recommendation=RecommendationLabel(decision.recommendation.value),
            total_score=_f(decision.final_score),
            confidence_score=_f(decision.confidence),
            technical_score=_category_score(decision, CATEGORY_LABELS["technical"]),
            fundamental_score=_category_score(decision, CATEGORY_LABELS["fundamental"]),
            momentum_score=_category_score(decision, CATEGORY_LABELS["momentum"]),
            volume_score=_category_score(decision, CATEGORY_LABELS["volume"]),
            risk_score=_category_score(decision, CATEGORY_LABELS["risk"]),
            contributor_breakdown=_serialize_breakdown(decision.breakdown),
            signals=_serialize_signals(decision.signals),
            reasons=list(decision.reasons),
            target_price=_f(decision.target_price),
            stop_loss=_f(decision.stop_loss),
            expected_return_pct=_f(decision.expected_return_pct),
            time_horizon=decision.time_horizon.value,
            risk_level=decision.risk_level.value,
            position_size=decision.position_size.value,
            engine_version=champion_snapshot.engine_version,
            calibration_version=challenger_config.version,
            source=champion_snapshot.source,
            variant=CHALLENGER_VARIANT,
            is_paper_trade=True,
        )
        session.add(challenger_snapshot)
        champion_snapshot.variant = CHAMPION_VARIANT
        create_pending_outcomes(session, challenger_snapshot)
        return challenger_snapshot
    except Exception:
        logger.exception(
            "Challenger snapshot generation failed for '%s' (config %s)",
            champion_snapshot.symbol, challenger_config.version,
        )
        return None


@dataclass(frozen=True)
class TwoSampleSignificanceResult:
    champion_sample_size: int
    champion_win_rate: Optional[float]
    challenger_sample_size: int
    challenger_win_rate: Optional[float]
    z_score: Optional[float]
    p_value: Optional[float]
    significant: bool


def two_sample_significance_test(
    champion_successes: int,
    champion_sample_size: int,
    challenger_successes: int,
    challenger_sample_size: int,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> TwoSampleSignificanceResult:
    """One-sided, pooled-variance two-proportion z-test: is the
    challenger's win rate significantly *higher* than the champion's?
    `significant` additionally requires both samples to meet
    `min_sample_size` and the challenger's observed rate to actually
    exceed the champion's -- the same "p-value AND minimum sample"
    discipline `pattern_discovery.proportion_significance_test` and
    `statistical_calibration.significance_test` already use."""
    if champion_sample_size < 2 or challenger_sample_size < 2:
        return TwoSampleSignificanceResult(
            champion_sample_size=champion_sample_size, champion_win_rate=None,
            challenger_sample_size=challenger_sample_size, challenger_win_rate=None,
            z_score=None, p_value=None, significant=False,
        )

    champion_rate = champion_successes / champion_sample_size
    challenger_rate = challenger_successes / challenger_sample_size
    pooled_rate = (champion_successes + challenger_successes) / (champion_sample_size + challenger_sample_size)
    standard_error = math.sqrt(
        pooled_rate * (1.0 - pooled_rate) * (1.0 / champion_sample_size + 1.0 / challenger_sample_size)
    )

    if standard_error == 0:
        return TwoSampleSignificanceResult(
            champion_sample_size=champion_sample_size, champion_win_rate=champion_rate,
            challenger_sample_size=challenger_sample_size, challenger_win_rate=challenger_rate,
            z_score=None, p_value=None, significant=False,
        )

    z_score = (challenger_rate - champion_rate) / standard_error
    p_value = 1.0 - statistics.NormalDist().cdf(z_score)
    significant = (
        p_value < significance_level
        and champion_sample_size >= min_sample_size
        and challenger_sample_size >= min_sample_size
        and challenger_rate > champion_rate
    )
    return TwoSampleSignificanceResult(
        champion_sample_size=champion_sample_size, champion_win_rate=champion_rate,
        challenger_sample_size=challenger_sample_size, challenger_win_rate=challenger_rate,
        z_score=z_score, p_value=p_value, significant=significant,
    )


def _terminal_labels(session: Session, variant: str, evaluation_horizon_days: int) -> List[bool]:
    rows = (
        session.query(RecommendationOutcome.status)
        .join(RecommendationSnapshot, RecommendationSnapshot.id == RecommendationOutcome.snapshot_id)
        .filter(
            RecommendationSnapshot.variant == variant,
            RecommendationOutcome.evaluation_horizon_days == evaluation_horizon_days,
            RecommendationOutcome.status.in_(_TERMINAL_STATUSES),
        )
        .all()
    )
    return [status is RecommendationOutcomeStatus.SUCCESSFUL for (status,) in rows]


def compare_champion_vs_challenger(
    session: Session,
    evaluation_horizon_days: int = DEFAULT_EVALUATION_HORIZON_DAYS,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> TwoSampleSignificanceResult:
    """Loads terminal (SUCCESSFUL/FAILED) outcomes for every champion
    and challenger snapshot at `evaluation_horizon_days` and runs the
    two-sample test. Purely descriptive -- a human reads this result to
    decide whether to call the existing, unchanged
    `CalibrationEngine.activate()`; nothing here activates anything."""
    champion_labels = _terminal_labels(session, CHAMPION_VARIANT, evaluation_horizon_days)
    challenger_labels = _terminal_labels(session, CHALLENGER_VARIANT, evaluation_horizon_days)
    return two_sample_significance_test(
        champion_successes=sum(1 for label in champion_labels if label),
        champion_sample_size=len(champion_labels),
        challenger_successes=sum(1 for label in challenger_labels if label),
        challenger_sample_size=len(challenger_labels),
        min_sample_size=min_sample_size,
        significance_level=significance_level,
    )
