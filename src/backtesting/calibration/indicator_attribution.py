"""indicator_attribution: replays the same historical, anti-look-ahead
data BacktestingEngine already walks, but scores each of the eleven
named indicators' OWN standalone predictive power in isolation (via
indicator_signals.py) instead of the blended AIDecisionEngine
recommendation -- "how good is Fibonacci on its own," not "how good is
the whole platform." Reuses every existing safety mechanism
(anti-look-ahead src.backtesting.data_access, provenance-matching) and
every existing metric formula (src.backtesting.metrics) rather than
duplicating either; the only new logic here is the (symbol, date) grid
walk and per-indicator bucketing.

Two distinct report shapes, matching indicator_signals.py's own two
disclosed indicator categories:
  - `directional_indicators`: the nine indicators that make a genuine
    BULLISH/BEARISH/NEUTRAL claim get the full metrics.compute_all_metrics()
    report (win rate, average return, drawdown, Sharpe, precision/
    recall, calibration/confidence accuracy, ...), computed completely
    independently per indicator.
  - `risk_indicators`: ATR and Bollinger Band width make no directional
    claim in this codebase (see RiskScoreContributor) -- their real
    claim is about forward *volatility*, so they get a volatility-
    bucket report (does a "low" reading actually precede calmer
    forward price action than a "high" reading) instead of a
    win-rate-shaped one that would misrepresent what they predict.
"""

import statistics
from dataclasses import dataclass
from datetime import date
from typing import Dict, List

from sqlalchemy.orm import Session

from src.backtesting.calibration.indicator_signals import (
    DIRECTIONAL_INDICATORS,
    RISK_INDICATORS,
    read_all_indicators,
)
from src.backtesting.data_access import (
    DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    collect_as_of_evaluations,
    load_forward_price_path,
)
from src.backtesting.metrics import EvaluationOutcome, compute_all_metrics
from src.domain.models import DataProvenanceMode

# Matches RiskScoreContributor's own ATR-ratio / Bollinger-width-ratio
# bands (see src/analysis/decision/contributors/risk_contributor.py) --
# the same real thresholds production already treats as "low/moderate/
# high" risk, reused here as the volatility buckets those thresholds
# are being tested against.
_RISK_BUCKET_THRESHOLDS = {
    "atr": {"low": 0.012, "high": 0.03},
    "bollinger": {"low": 0.04, "high": 0.10},
}

_DIRECTION_TO_RECOMMENDATION = {"BULLISH": "BUY", "BEARISH": "SELL", "NEUTRAL": "HOLD"}


@dataclass(frozen=True)
class IndicatorAttributionReport:
    evaluated_count: int
    skipped: Dict[str, int]
    directional_indicators: Dict[str, Dict]
    risk_indicators: Dict[str, Dict]


def _forward_return_pct(entry_price, holding_df):
    """Deliberately cost-free (unlike engine.py's own forward-return
    calculation, which subtracts a configured transaction cost) -- an
    indicator's raw standalone predictive quality is a property of the
    indicator, not of whether a real trade with real costs was ever
    executed on it."""
    if entry_price is None or entry_price <= 0 or holding_df is None or holding_df.empty:
        return None
    exit_price = float(holding_df["close"].iloc[-1])
    return (exit_price - entry_price) / entry_price * 100.0


def _risk_bucket(indicator: str, ratio: float) -> str:
    bounds = _RISK_BUCKET_THRESHOLDS[indicator]
    if ratio <= bounds["low"]:
        return "low"
    if ratio >= bounds["high"]:
        return "high"
    return "moderate"


def _volatility_bucket_report(buckets: Dict[str, List[float]]) -> Dict[str, Dict]:
    report = {}
    for bucket_name, values in buckets.items():
        if not values:
            continue
        report[bucket_name] = {
            "sample_size": len(values),
            "average_forward_return_pct": statistics.mean(values),
            "realized_volatility": statistics.stdev(values) if len(values) >= 2 else None,
        }
    return report


def run_indicator_attribution(
    session: Session,
    symbols: List[str],
    start_date: date,
    end_date: date,
    data_provenance_mode: DataProvenanceMode,
    evaluation_frequency_days: int = 7,
    holding_horizon_days: int = 20,
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
) -> IndicatorAttributionReport:
    evaluations, skipped = collect_as_of_evaluations(
        session, symbols, start_date, end_date, evaluation_frequency_days,
        data_provenance_mode, fundamental_reporting_lag_days,
    )

    directional_outcomes: Dict[str, List[EvaluationOutcome]] = {name: [] for name in DIRECTIONAL_INDICATORS}
    risk_buckets: Dict[str, Dict[str, List[float]]] = {
        name: {"low": [], "moderate": [], "high": []} for name in RISK_INDICATORS
    }
    evaluated_count = 0

    for evaluation in evaluations:
        dataset = evaluation.dataset
        if dataset.context.technical_result is None:
            skipped["insufficient_data"] += 1
            continue

        readings = read_all_indicators(dataset)
        if not readings:
            skipped["insufficient_data"] += 1
            continue

        holding_df = load_forward_price_path(session, evaluation.stock, evaluation.eval_date, holding_horizon_days)
        forward_return = _forward_return_pct(dataset.context.latest_price, holding_df)
        evaluated_count += 1

        for name, call in readings.items():
            if name in RISK_INDICATORS:
                if forward_return is not None and call.magnitude is not None:
                    risk_buckets[name][_risk_bucket(name, call.magnitude)].append(forward_return)
                continue

            directional_outcomes[name].append(
                EvaluationOutcome(
                    symbol=evaluation.symbol,
                    evaluated_at=evaluation.eval_date,
                    recommendation=_DIRECTION_TO_RECOMMENDATION[call.direction],
                    confidence=call.magnitude or 0.0,
                    total_score=50.0,
                    forward_return_pct=forward_return,
                )
            )

    return IndicatorAttributionReport(
        evaluated_count=evaluated_count,
        skipped=skipped,
        directional_indicators={name: compute_all_metrics(outcomes) for name, outcomes in directional_outcomes.items()},
        risk_indicators={name: _volatility_bucket_report(buckets) for name, buckets in risk_buckets.items()},
    )
