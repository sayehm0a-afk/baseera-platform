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
"""

import statistics
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List, Optional

_BULLISH = {"STRONG_BUY", "BUY"}
_BEARISH = {"STRONG_SELL", "SELL"}

_CONFIDENCE_BUCKET_EDGES = [0, 20, 40, 60, 80, 100]


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
        "by_risk_level": breakdown_by(outcomes, lambda o: o.risk_level),
        "by_time_horizon": breakdown_by(outcomes, lambda o: o.time_horizon),
        "by_sector": breakdown_by(outcomes, lambda o: o.sector),
        "by_symbol": breakdown_by(outcomes, lambda o: o.symbol),
        "by_market_regime": breakdown_by(outcomes, lambda o: o.market_regime),
    }
