"""Pure statistics over a list of EvaluationOutcomes -- no database, no
network, no engine calls. Every function here takes data already
computed by BacktestingEngine and returns a number or a small dict;
this separation is what makes the metric formulas independently unit-
testable with hand-built fixtures instead of a full backtest run.

Metric definitions (also documented in docs/BACKTESTING_AND_CALIBRATION.md):

- direction accuracy: of BUY-like/SELL-like calls with a known forward
  return, the fraction whose sign matched the call's implied direction.
  HOLD calls make no directional claim and are excluded.
- target-price hit rate / stop-loss hit rate: of calls where that
  price level was set and the outcome is known, the fraction that were
  touched within their configured horizon.
- forward return: the % price change from the evaluation price to the
  price `holding_horizon_days` later.
- win rate / loss rate: of directional (non-HOLD) calls, the fraction
  whose *directional* P&L (see `_directional_pnl_pct`) was positive /
  negative.
- profit factor: sum of positive directional P&L / abs(sum of negative
  directional P&L). `None` if there were no losing calls (undefined,
  not infinite -- avoids a misleading "infinite edge" figure) or no
  calls at all.
- max drawdown: the largest peak-to-trough decline of a *discrete
  trade-sequence* equity curve built by compounding each call's
  directional P&L in evaluation-date order, equal-weighted. This is a
  simplification, not a true position-sized portfolio simulation
  (there is no portfolio model in this codebase) -- disclosed here and
  in the docs, not presented as a realistic portfolio drawdown.
- volatility: sample standard deviation of the directional P&L series.
- downside deviation: sample standard deviation of only the negative
  values in that series (a Sortino-ratio input).
- Sharpe / Sortino ratio: mean directional P&L (minus an optional
  risk-free rate) divided by volatility / downside deviation.
  Non-annualized unless `periods_per_year` is supplied.
- calibration error: mean absolute difference between a confidence
  bucket's average stated confidence and its realized direction
  accuracy, weighted by bucket size (a standard Expected Calibration
  Error, ECE).
- maximum calibration error (MCE): the single worst bucket's
  confidence-vs-accuracy gap, rather than ECE's count-weighted average
  -- the complementary "how bad does it get" figure.
- Brier score: mean squared error between each call's own exact stated
  confidence (as a 0-1 probability) and its realized binary outcome --
  a proper scoring rule using every call individually, not bucketed.
- reliability diagram data: `confidence_buckets()`'s output reshaped
  into plain 0-1-scale predicted/actual pairs for chart rendering.
- precision / recall: standard binary-classification metrics treating
  each directional call as a prediction and the sign of the realized
  forward return as ground truth. Bullish calls (predicting an UP
  move) and bearish calls (predicting a DOWN move) are two independent
  classes -- a BUY call has no opinion about the DOWN class and is
  never counted against it -- scored separately, then macro-averaged.
  HOLD calls and zero/unknown forward returns make no directional
  claim and are excluded from both.
- position sizing quality: buckets directional calls with a known
  outcome by their recorded `position_size` and compares each
  bucket's win rate / average directional P&L -- a well-calibrated
  sizing rule should show larger sizes earning better (or at least not
  worse) outcomes than smaller ones, since size is meant to track
  conviction quality, not just be a fixed multiplier. `monotonicity_score`
  is the Pearson correlation between the size ordinal (NONE=0 ...
  LARGE=4) and each bucket's average directional P&L -- close to +1
  means sizing is well-calibrated, near 0 or negative means it is not.
"""

import statistics
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List, Optional

_BULLISH = {"STRONG_BUY", "BUY"}
_BEARISH = {"STRONG_SELL", "SELL"}

_CONFIDENCE_BUCKET_EDGES = [0, 20, 40, 60, 80, 100]
_POSITION_SIZE_ORDER = ["NONE", "SMALL", "MODERATE", "STANDARD", "LARGE"]


@dataclass(frozen=True)
class EvaluationOutcome:
    """One historical evaluation, decision, and (if forward data was
    available) its realized outcome. BacktestingEngine builds these;
    every function below only reads them."""

    symbol: str
    evaluated_at: date
    recommendation: str
    confidence: float
    total_score: float
    risk_level: Optional[str] = None
    time_horizon: Optional[str] = None
    sector: Optional[str] = None
    market_regime: Optional[str] = None
    market_price_at_evaluation: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    forward_return_pct: Optional[float] = None
    hit_target: Optional[bool] = None
    hit_stop_loss: Optional[bool] = None
    position_size: Optional[str] = None


def _is_bullish(recommendation: str) -> bool:
    return recommendation in _BULLISH


def _is_bearish(recommendation: str) -> bool:
    return recommendation in _BEARISH


def _directional_pnl_pct(outcome: EvaluationOutcome) -> Optional[float]:
    """The P&L % implied by acting on this call, signed so a correct
    call is positive regardless of direction -- e.g. a SELL call
    followed by a price decline is a *positive* directional P&L. `None`
    for HOLD (no position implied) or when the forward return itself
    is unknown."""
    if outcome.forward_return_pct is None:
        return None
    if _is_bullish(outcome.recommendation):
        return outcome.forward_return_pct
    if _is_bearish(outcome.recommendation):
        return -outcome.forward_return_pct
    return None  # HOLD


def direction_accuracy(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    directional = [o for o in outcomes if (_is_bullish(o.recommendation) or _is_bearish(o.recommendation)) and o.forward_return_pct is not None]
    if not directional:
        return None
    correct = sum(1 for o in directional if _directional_pnl_pct(o) > 0)
    return correct / len(directional)


def _hit_rate(outcomes: List[EvaluationOutcome], field_name: str) -> Optional[float]:
    known = [getattr(o, field_name) for o in outcomes if getattr(o, field_name) is not None]
    if not known:
        return None
    return sum(1 for hit in known if hit) / len(known)


def target_price_hit_rate(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    return _hit_rate(outcomes, "hit_target")


def stop_loss_hit_rate(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    return _hit_rate(outcomes, "hit_stop_loss")


def average_forward_return(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    values = [o.forward_return_pct for o in outcomes if o.forward_return_pct is not None]
    return statistics.mean(values) if values else None


def median_forward_return(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    values = [o.forward_return_pct for o in outcomes if o.forward_return_pct is not None]
    return statistics.median(values) if values else None


def _directional_pnl_series(outcomes: List[EvaluationOutcome]) -> List[float]:
    return [pnl for o in sorted(outcomes, key=lambda x: x.evaluated_at) for pnl in [_directional_pnl_pct(o)] if pnl is not None]


def win_rate(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    pnl = _directional_pnl_series(outcomes)
    if not pnl:
        return None
    return sum(1 for p in pnl if p > 0) / len(pnl)


def loss_rate(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    wr = win_rate(outcomes)
    return None if wr is None else 1.0 - wr


def profit_factor(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    pnl = _directional_pnl_series(outcomes)
    if not pnl:
        return None
    gains = sum(p for p in pnl if p > 0)
    losses = sum(-p for p in pnl if p < 0)
    if losses == 0:
        return None  # undefined (no losing trades) -- never report as infinite
    return gains / losses


def max_drawdown(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    """Peak-to-trough decline (as a negative fraction, e.g. -0.18 for
    an 18% drawdown) of the discrete, equal-weighted, compounded
    directional-P&L equity curve. See module docstring for the
    simplification this represents."""
    pnl = _directional_pnl_series(outcomes)
    if not pnl:
        return None

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for p in pnl:
        equity *= 1.0 + p / 100.0
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak
        max_dd = min(max_dd, drawdown)
    return max_dd


def directional_pnl_values(outcomes: List[EvaluationOutcome]) -> List[float]:
    """The raw, signed per-call directional P&L series win_rate/
    profit_factor/sharpe_ratio/etc. are all built from -- exposed
    publicly so a caller that genuinely needs the raw values (e.g. a
    significance test in src.backtesting.calibration.statistical_calibration)
    doesn't have to re-derive the same sign convention a second time."""
    return _directional_pnl_series(outcomes)


def volatility(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    pnl = _directional_pnl_series(outcomes)
    if len(pnl) < 2:
        return None
    return statistics.stdev(pnl)


def downside_deviation(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    pnl = _directional_pnl_series(outcomes)
    negative = [p for p in pnl if p < 0]
    if len(negative) < 2:
        return None
    return statistics.stdev(negative)


def sharpe_ratio(
    outcomes: List[EvaluationOutcome], risk_free_rate_pct: float = 0.0, periods_per_year: Optional[float] = None
) -> Optional[float]:
    pnl = _directional_pnl_series(outcomes)
    if len(pnl) < 2:
        return None
    excess = [p - risk_free_rate_pct for p in pnl]
    std = statistics.stdev(excess)
    if std == 0:
        return None
    ratio = statistics.mean(excess) / std
    return ratio * (periods_per_year ** 0.5) if periods_per_year else ratio


def sortino_ratio(
    outcomes: List[EvaluationOutcome], risk_free_rate_pct: float = 0.0, periods_per_year: Optional[float] = None
) -> Optional[float]:
    pnl = _directional_pnl_series(outcomes)
    if not pnl:
        return None
    excess = [p - risk_free_rate_pct for p in pnl]
    downside = [e for e in excess if e < 0]
    if len(downside) < 2:
        return None
    dd = statistics.stdev(downside)
    if dd == 0:
        return None
    ratio = statistics.mean(excess) / dd
    return ratio * (periods_per_year ** 0.5) if periods_per_year else ratio


def confidence_buckets(outcomes: List[EvaluationOutcome]) -> List[Dict]:
    """Groups directional calls with a known outcome into confidence
    bands and reports each band's realized direction accuracy --
    the raw material for calibration_error() and for a human to eyeball
    "does 80%+ confidence actually mean ~80% right"."""
    directional = [
        o for o in outcomes
        if (_is_bullish(o.recommendation) or _is_bearish(o.recommendation)) and o.forward_return_pct is not None
    ]
    buckets = []
    for low, high in zip(_CONFIDENCE_BUCKET_EDGES[:-1], _CONFIDENCE_BUCKET_EDGES[1:]):
        in_bucket = [o for o in directional if low <= o.confidence < high or (high == 100 and o.confidence == 100)]
        if not in_bucket:
            continue
        correct = sum(1 for o in in_bucket if _directional_pnl_pct(o) > 0)
        buckets.append(
            {
                "confidence_range": f"{low}-{high}",
                "count": len(in_bucket),
                "mean_confidence": statistics.mean(o.confidence for o in in_bucket),
                "realized_accuracy": correct / len(in_bucket),
            }
        )
    return buckets


def calibration_error(outcomes: List[EvaluationOutcome]) -> Optional[Dict]:
    buckets = confidence_buckets(outcomes)
    if not buckets:
        return None
    total = sum(b["count"] for b in buckets)
    weighted_error = sum(
        b["count"] * abs(b["mean_confidence"] / 100.0 - b["realized_accuracy"]) for b in buckets
    )
    return {"overall_error": weighted_error / total, "buckets": buckets}


def maximum_calibration_error(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    """MCE: the single worst-calibrated confidence bucket's gap between
    stated confidence and realized accuracy -- `calibration_error()`
    (ECE) is the count-weighted *average* gap across all buckets, which
    a single badly-miscalibrated-but-small bucket can hide; MCE is the
    complementary "how bad does it get in the worst case" number, the
    same relationship ECE/MCE have in the calibration literature."""
    buckets = confidence_buckets(outcomes)
    if not buckets:
        return None
    return max(abs(b["mean_confidence"] / 100.0 - b["realized_accuracy"]) for b in buckets)


def reliability_diagram_data(outcomes: List[EvaluationOutcome]) -> List[Dict]:
    """`confidence_buckets()`'s output reshaped into the plain
    predicted-vs-actual pairs a reliability-diagram chart needs (both
    on a 0-1 scale, plus the bucket's sample count for point sizing) --
    no new computation, purely a presentation-layer reformat so a
    frontend/dashboard never has to know `confidence_buckets()`'s
    internal field names."""
    return [
        {
            "confidence_range": b["confidence_range"],
            "predicted": b["mean_confidence"] / 100.0,
            "actual": b["realized_accuracy"],
            "count": b["count"],
        }
        for b in confidence_buckets(outcomes)
    ]


def brier_score(outcomes: List[EvaluationOutcome]) -> Optional[float]:
    """Mean squared error between stated confidence (as a 0-1
    probability the call is directionally correct) and the realized
    binary outcome (1 if the call's directional P&L was positive, 0
    otherwise) -- the standard proper scoring rule for a probabilistic
    forecast, lower is better, 0 is perfect. Unlike ECE/MCE (which
    only see confidence through 5 coarse buckets), Brier score uses
    every call's exact stated confidence, so it can move even when no
    bucket's aggregate accuracy does."""
    directional = [
        o for o in outcomes
        if (_is_bullish(o.recommendation) or _is_bearish(o.recommendation)) and o.forward_return_pct is not None
    ]
    if not directional:
        return None
    squared_errors = [
        ((o.confidence / 100.0) - (1.0 if _directional_pnl_pct(o) > 0 else 0.0)) ** 2 for o in directional
    ]
    return statistics.mean(squared_errors)


def _class_precision_recall(known: List[EvaluationOutcome], is_predicted: Callable, is_actual: Callable) -> Dict:
    predicted_positive = [o for o in known if is_predicted(o)]
    actual_positive = [o for o in known if is_actual(o)]
    true_positive = [o for o in predicted_positive if is_actual(o)]
    return {
        "precision": len(true_positive) / len(predicted_positive) if predicted_positive else None,
        "recall": len(true_positive) / len(actual_positive) if actual_positive else None,
        "predicted_count": len(predicted_positive),
        "actual_count": len(actual_positive),
    }


def precision_recall(outcomes: List[EvaluationOutcome]) -> Optional[Dict]:
    known = [o for o in outcomes if o.forward_return_pct is not None and o.forward_return_pct != 0]
    if not known:
        return None

    bullish = _class_precision_recall(known, lambda o: _is_bullish(o.recommendation), lambda o: o.forward_return_pct > 0)
    bearish = _class_precision_recall(known, lambda o: _is_bearish(o.recommendation), lambda o: o.forward_return_pct < 0)

    precisions = [m["precision"] for m in (bullish, bearish) if m["precision"] is not None]
    recalls = [m["recall"] for m in (bullish, bearish) if m["recall"] is not None]

    return {
        "bullish": bullish,
        "bearish": bearish,
        "macro_precision": statistics.mean(precisions) if precisions else None,
        "macro_recall": statistics.mean(recalls) if recalls else None,
        "sample_size": len(known),
    }


def position_sizing_quality(outcomes: List[EvaluationOutcome]) -> Optional[Dict]:
    directional = [
        o for o in outcomes
        if o.position_size in _POSITION_SIZE_ORDER
        and (_is_bullish(o.recommendation) or _is_bearish(o.recommendation))
        and o.forward_return_pct is not None
    ]
    if not directional:
        return None

    buckets: Dict[str, Dict] = {}
    for size in _POSITION_SIZE_ORDER:
        in_bucket = [o for o in directional if o.position_size == size]
        pnl = [p for o in in_bucket for p in [_directional_pnl_pct(o)] if p is not None]
        if not pnl:
            continue
        buckets[size] = {
            "count": len(pnl),
            "win_rate": sum(1 for p in pnl if p > 0) / len(pnl),
            "average_directional_pnl_pct": statistics.mean(pnl),
        }

    monotonicity_score = None
    if len(buckets) >= 2:
        ordinals = [float(_POSITION_SIZE_ORDER.index(size)) for size in buckets]
        pnls = [buckets[size]["average_directional_pnl_pct"] for size in buckets]
        if len(set(ordinals)) > 1 and len(set(pnls)) > 1:
            monotonicity_score = statistics.correlation(ordinals, pnls)

    return {"buckets": buckets, "monotonicity_score": monotonicity_score}


def breakdown_by(outcomes: List[EvaluationOutcome], key_fn: Callable[[EvaluationOutcome], Optional[str]]) -> Dict[str, Dict]:
    """Groups outcomes by an arbitrary key (recommendation class, risk
    level, time horizon, sector, symbol, market regime, ...) and
    computes the same headline metrics per group. Outcomes whose key is
    `None` are grouped under "UNKNOWN" rather than silently dropped."""
    groups: Dict[str, List[EvaluationOutcome]] = {}
    for outcome in outcomes:
        key = key_fn(outcome) or "UNKNOWN"
        groups.setdefault(key, []).append(outcome)

    return {key: compute_all_metrics(group_outcomes) for key, group_outcomes in groups.items()}


def compute_all_metrics(outcomes: List[EvaluationOutcome]) -> Dict:
    """The full metrics dict BacktestRun.metrics stores -- every
    headline number plus the standard breakdowns."""
    return {
        "evaluation_count": len(outcomes),
        "direction_accuracy": direction_accuracy(outcomes),
        "target_price_hit_rate": target_price_hit_rate(outcomes),
        "stop_loss_hit_rate": stop_loss_hit_rate(outcomes),
        "average_forward_return_pct": average_forward_return(outcomes),
        "median_forward_return_pct": median_forward_return(outcomes),
        "win_rate": win_rate(outcomes),
        "loss_rate": loss_rate(outcomes),
        "profit_factor": profit_factor(outcomes),
        "max_drawdown": max_drawdown(outcomes),
        "volatility": volatility(outcomes),
        "downside_deviation": downside_deviation(outcomes),
        "sharpe_ratio": sharpe_ratio(outcomes),
        "sortino_ratio": sortino_ratio(outcomes),
        "calibration_error": calibration_error(outcomes),
        "maximum_calibration_error": maximum_calibration_error(outcomes),
        "brier_score": brier_score(outcomes),
        "precision_recall": precision_recall(outcomes),
        "position_sizing_quality": position_sizing_quality(outcomes),
    }


def full_report(outcomes: List[EvaluationOutcome]) -> Dict:
    """`compute_all_metrics()` plus every requested breakdown --
    recommendation class, confidence range, risk level, time horizon,
    sector, symbol, market regime."""
    return {
        "overall": compute_all_metrics(outcomes),
        "by_recommendation": breakdown_by(outcomes, lambda o: o.recommendation),
        "by_confidence_bucket": {
            b["confidence_range"]: b for b in confidence_buckets(outcomes)
        },
        "reliability_diagram": reliability_diagram_data(outcomes),
        "by_risk_level": breakdown_by(outcomes, lambda o: o.risk_level),
        "by_time_horizon": breakdown_by(outcomes, lambda o: o.time_horizon),
        "by_sector": breakdown_by(outcomes, lambda o: o.sector),
        "by_symbol": breakdown_by(outcomes, lambda o: o.symbol),
        "by_market_regime": breakdown_by(outcomes, lambda o: o.market_regime),
    }
