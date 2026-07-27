"""statistical_calibration: proposes new contributor weights from real
historical evidence, replacing the heuristic default weights only
where a significance test says the evidence actually supports it.

Distinct from `CalibrationEngine.propose_random_candidates()` (which
samples candidates uniformly at random from a caller-supplied range
and lets `validate()`'s same-period backtest comparison decide if one
happens to be better) -- this module instead *measures* each of the
eleven scoring contributors' own standalone directional edge (mean
signed P&L of acting on that contributor alone, exactly as
src.backtesting.baselines.TechnicalOnlyStrategy/FundamentalOnlyStrategy
already isolate two of them) over a training period, tests whether
that edge is statistically distinguishable from zero, and proposes a
new weight only for contributors that pass. A contributor with too
little backtestable data (the four external-factor contributors --
news/macro/insider/sector-rotation -- have no real news/macro/insider/
sector feed wired into src.backtesting.data_access, so they score
`None` on every historical replay) or a non-significant edge keeps its
exact existing weight, disclosed as "insufficient evidence" rather
than silently left out of the report.

The resulting `contributor_weights` dict is the exact shape
src.backtesting.calibration.parameters.build_contributors() already
consumes, and is meant to be handed straight to
CalibrationEngine.propose() as a `config["contributor_weights"]`
payload -- this module measures and proposes; the existing propose ->
validate -> activate -> rollback lifecycle still governs whether a
proposal actually reaches production, unchanged. This is what makes
the engine reusable for continuous improvement: any later date range
with newly ingested market data can be handed to
propose_statistical_weights() again to produce a fresh, independently
re-validated candidate.

No scipy dependency: `statistics.NormalDist` (Python 3.8+ stdlib)
supplies the standard normal CDF a two-sided z-test needs. This is the
normal approximation to the one-sample t-test -- exact as sample size
grows, and the conventional, textbook-standard approximation once
n >= ~30, which is exactly this module's own default minimum sample
size floor.
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.analysis.decision.ai_decision_engine import default_contributors
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.backtesting.calibration.parameters import contributor_class, contributor_names
from src.backtesting.data_access import (
    DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    collect_as_of_evaluations,
    load_forward_price_path,
)
from src.backtesting.metrics import EvaluationOutcome, directional_pnl_values
from src.domain.models import DataProvenanceMode

# The conventional threshold for the normal approximation to the
# t-distribution to be trustworthy, and (not coincidentally) a
# reasonable minimum sample size for any statistical claim about a
# trading edge to be taken seriously at all.
DEFAULT_MIN_SAMPLE_SIZE = 30
DEFAULT_SIGNIFICANCE_LEVEL = 0.05

# Bounds how much a single statistically-significant t-statistic can
# move a contributor's weight in one calibration pass -- a t-stat of
# 5+ (already a very strong signal) saturates the adjustment rather
# than letting an extreme outlier run away with the weight; disclosed,
# bounded, not fabricated precision.
_MAX_WEIGHT_ADJUSTMENT = 0.5
_EDGE_SCALE_DIVISOR = 10.0
_MIN_WEIGHT_FLOOR = 0.01


def _forward_return_pct(entry_price: Optional[float], holding_df) -> Optional[float]:
    if entry_price is None or entry_price <= 0 or holding_df is None or holding_df.empty:
        return None
    exit_price = float(holding_df["close"].iloc[-1])
    return (exit_price - entry_price) / entry_price * 100.0


@dataclass(frozen=True)
class SignificanceResult:
    sample_size: int
    mean_edge: Optional[float]
    t_statistic: Optional[float]
    p_value: Optional[float]
    significant: bool


def significance_test(
    values: List[float], min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE, significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL
) -> SignificanceResult:
    """Two-sided one-sample z-test of `values`' mean against zero (the
    null hypothesis: no real directional edge). `significant` requires
    both a sub-`significance_level` p-value AND at least
    `min_sample_size` observations -- a low p-value from a handful of
    lucky calls is not evidence, regardless of what the arithmetic
    says."""
    n = len(values)
    if n < 2:
        return SignificanceResult(sample_size=n, mean_edge=None, t_statistic=None, p_value=None, significant=False)

    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    if stdev == 0:
        return SignificanceResult(sample_size=n, mean_edge=mean, t_statistic=None, p_value=None, significant=False)

    standard_error = stdev / math.sqrt(n)
    t_statistic = mean / standard_error
    p_value = 2.0 * (1.0 - statistics.NormalDist().cdf(abs(t_statistic)))
    significant = p_value < significance_level and n >= min_sample_size
    return SignificanceResult(
        sample_size=n, mean_edge=mean, t_statistic=t_statistic, p_value=p_value, significant=significant
    )


@dataclass(frozen=True)
class ContributorCalibrationEntry:
    contributor: str
    old_weight: float
    new_weight: float
    sample_size: int
    mean_edge: Optional[float]
    t_statistic: Optional[float]
    p_value: Optional[float]
    significant: bool
    action: str  # "reweighted" | "unchanged_insufficient_evidence" | "unchanged_not_significant"


@dataclass(frozen=True)
class StatisticalCalibrationReport:
    training_period_start: date
    training_period_end: date
    symbols: List[str]
    entries: List[ContributorCalibrationEntry] = field(default_factory=list)

    @property
    def contributor_weights(self) -> Dict[str, float]:
        """Only the contributors this run actually reweighted -- the
        exact `config["contributor_weights"]` payload shape
        CalibrationEngine.propose() expects; unchanged contributors are
        deliberately omitted so build_contributors() falls back to
        their own engine default, not a needlessly-repeated value."""
        return {e.contributor: e.new_weight for e in self.entries if e.action == "reweighted"}


def _propose_weight(old_weight: float, significance: SignificanceResult) -> float:
    edge_scale = max(-_MAX_WEIGHT_ADJUSTMENT, min(_MAX_WEIGHT_ADJUSTMENT, significance.t_statistic / _EDGE_SCALE_DIVISOR))
    return max(_MIN_WEIGHT_FLOOR, round(old_weight * (1.0 + edge_scale), 4))


def propose_statistical_weights(
    session: Session,
    symbols: List[str],
    training_period_start: date,
    training_period_end: date,
    data_provenance_mode: DataProvenanceMode,
    evaluation_frequency_days: int = 7,
    holding_horizon_days: int = 20,
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> StatisticalCalibrationReport:
    evaluations, _skipped = collect_as_of_evaluations(
        session, symbols, training_period_start, training_period_end, evaluation_frequency_days,
        data_provenance_mode, fundamental_reporting_lag_days,
    )

    default_weights = {c.name: c.default_weight for c in default_contributors()}
    entries: List[ContributorCalibrationEntry] = []

    for name in contributor_names():
        contributor_cls = contributor_class(name)
        old_weight = default_weights[name]
        single_contributor_engine = RecommendationEngine(contributors=[contributor_cls(weight=1.0)])

        outcomes: List[EvaluationOutcome] = []
        for evaluation in evaluations:
            result = single_contributor_engine.generate(evaluation.dataset.context)
            if result.contributions[0].score is None:
                continue  # this contributor had no data for this evaluation -- not a data point

            holding_df = load_forward_price_path(session, evaluation.stock, evaluation.eval_date, holding_horizon_days)
            outcomes.append(
                EvaluationOutcome(
                    symbol=evaluation.symbol,
                    evaluated_at=evaluation.eval_date,
                    recommendation=result.recommendation.value,
                    confidence=result.confidence,
                    total_score=result.final_score,
                    forward_return_pct=_forward_return_pct(evaluation.dataset.context.latest_price, holding_df),
                )
            )

        significance = significance_test(directional_pnl_values(outcomes), min_sample_size, significance_level)

        if significance.significant:
            action = "reweighted"
            new_weight = _propose_weight(old_weight, significance)
        elif significance.sample_size < min_sample_size:
            action = "unchanged_insufficient_evidence"
            new_weight = old_weight
        else:
            action = "unchanged_not_significant"
            new_weight = old_weight

        entries.append(
            ContributorCalibrationEntry(
                contributor=name, old_weight=old_weight, new_weight=new_weight,
                sample_size=significance.sample_size, mean_edge=significance.mean_edge,
                t_statistic=significance.t_statistic, p_value=significance.p_value,
                significant=significance.significant, action=action,
            )
        )

    return StatisticalCalibrationReport(
        training_period_start=training_period_start, training_period_end=training_period_end,
        symbols=symbols, entries=entries,
    )
