"""E5 of the AI Evolution Layer: discovers which signal conditions are
statistically associated with a significantly different win rate than
the population baseline, from real `RecommendationOutcome` history.

Generalizes `src.backtesting.calibration.statistical_calibration`'s
one-sample z-test approach (there: is a contributor's mean directional
P&L distinguishable from zero) to a one-sample z-test **for a
proportion** (here: is a signal's subgroup win rate distinguishable
from the population's baseline win rate) -- the natural generalization
for a binary SUCCESSFUL/FAILED label rather than a continuous P&L
value, same no-scipy `statistics.NormalDist()` technique.

Only one condition type is tested this milestone: "does the presence
of a specific named `Signal` (already recorded on every
`RecommendationSnapshot.signals` at write time, e.g. "RSI Oversold
Crossover", "MACD Bullish Cross") correlate with a different win rate
than average." This is a deliberately narrower scope than the original
request's "RSI ranges/MACD crossings/volume profiles/news sentiment/
market regimes/sectors" -- those specific numeric-range/regime/sector
breakdowns aren't yet populated as first-class, queryable fields on
live data (`market_regime` stays null until E7's regime tagging), so
testing them now would mean fabricating buckets rather than measuring
real recorded evidence. Signal names are real, already-recorded
evidence available today; extending to other condition types is
additive once their underlying fields are populated.

Never applied automatically to production weights or narration --
`discover_patterns()` only ever inserts/updates rows in
`discovered_patterns`; wiring a discovered pattern into
`CalibrationEngine.propose()` or the analyst framework's explanations
is a human-reviewed step, not automatic.
"""

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from src.domain.models import (
    DiscoveredPattern,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
)

DEFAULT_MIN_SAMPLE_SIZE = 30
DEFAULT_SIGNIFICANCE_LEVEL = 0.05
DEFAULT_EVALUATION_HORIZON_DAYS = 7

_TERMINAL_STATUSES = (RecommendationOutcomeStatus.SUCCESSFUL, RecommendationOutcomeStatus.FAILED)


@dataclass(frozen=True)
class ProportionSignificanceResult:
    sample_size: int
    observed_rate: Optional[float]
    baseline_rate: float
    z_score: Optional[float]
    p_value: Optional[float]
    significant: bool


def proportion_significance_test(
    successes: int,
    sample_size: int,
    baseline_rate: float,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> ProportionSignificanceResult:
    """Two-sided one-sample z-test of a sample proportion against a
    fixed baseline rate (the standard normal-approximation test for a
    binomial proportion) -- `significant` requires both a
    sub-`significance_level` p-value AND at least `min_sample_size`
    observations, same discipline as
    `statistical_calibration.significance_test()`."""
    if sample_size < 2 or baseline_rate <= 0.0 or baseline_rate >= 1.0:
        return ProportionSignificanceResult(
            sample_size=sample_size, observed_rate=None, baseline_rate=baseline_rate,
            z_score=None, p_value=None, significant=False,
        )

    observed_rate = successes / sample_size
    standard_error = math.sqrt(baseline_rate * (1.0 - baseline_rate) / sample_size)
    if standard_error == 0:
        return ProportionSignificanceResult(
            sample_size=sample_size, observed_rate=observed_rate, baseline_rate=baseline_rate,
            z_score=None, p_value=None, significant=False,
        )

    z_score = (observed_rate - baseline_rate) / standard_error
    p_value = 2.0 * (1.0 - statistics.NormalDist().cdf(abs(z_score)))
    significant = p_value < significance_level and sample_size >= min_sample_size
    return ProportionSignificanceResult(
        sample_size=sample_size, observed_rate=observed_rate, baseline_rate=baseline_rate,
        z_score=z_score, p_value=p_value, significant=significant,
    )


def _load_labeled_snapshots(session: Session, evaluation_horizon_days: int) -> List[tuple]:
    rows = (
        session.query(RecommendationSnapshot, RecommendationOutcome.status)
        .join(RecommendationOutcome, RecommendationOutcome.snapshot_id == RecommendationSnapshot.id)
        .filter(
            RecommendationOutcome.evaluation_horizon_days == evaluation_horizon_days,
            RecommendationOutcome.status.in_(_TERMINAL_STATUSES),
        )
        .all()
    )
    return [(snapshot, status is RecommendationOutcomeStatus.SUCCESSFUL) for snapshot, status in rows]


def _signal_names(snapshot: RecommendationSnapshot) -> Set[str]:
    if not snapshot.signals:
        return set()
    return {signal["name"] for signal in snapshot.signals if isinstance(signal, dict) and signal.get("name")}


def _upsert_pattern(
    session: Session,
    condition_type: str,
    condition_description: str,
    evaluation_horizon_days: int,
    result: ProportionSignificanceResult,
    now: datetime,
) -> DiscoveredPattern:
    row = (
        session.query(DiscoveredPattern)
        .filter_by(
            condition_type=condition_type,
            condition_description=condition_description,
            evaluation_horizon_days=evaluation_horizon_days,
        )
        .one_or_none()
    )
    if row is None:
        row = DiscoveredPattern(
            condition_type=condition_type,
            condition_description=condition_description,
            evaluation_horizon_days=evaluation_horizon_days,
        )
        session.add(row)

    row.sample_size = result.sample_size
    row.win_rate = result.observed_rate
    row.baseline_win_rate = result.baseline_rate
    row.z_score = result.z_score
    row.p_value = result.p_value
    row.still_valid = result.significant
    row.last_validated_at = now
    return row


def discover_patterns(
    session: Session,
    evaluation_horizon_days: int = DEFAULT_EVALUATION_HORIZON_DAYS,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> List[DiscoveredPattern]:
    """Tests every signal name that appears in at least
    `min_sample_size` labeled snapshots at `evaluation_horizon_days`.
    A signal already in `discovered_patterns` is re-tested and
    updated in place (rolling re-validation, `still_valid` reflects
    only the latest test) rather than duplicated; a signal that no
    longer tests significant keeps its row (audit trail) with
    `still_valid=False` rather than being deleted."""
    now = datetime.now(timezone.utc)
    labeled = _load_labeled_snapshots(session, evaluation_horizon_days)
    if not labeled:
        session.commit()
        return []

    baseline_rate = sum(1 for _, success in labeled if success) / len(labeled)

    signal_to_labels: Dict[str, List[bool]] = {}
    for snapshot, success in labeled:
        for name in _signal_names(snapshot):
            signal_to_labels.setdefault(name, []).append(success)

    updated_rows = []
    for signal_name, labels in signal_to_labels.items():
        if len(labels) < min_sample_size:
            continue
        result = proportion_significance_test(
            successes=sum(1 for label in labels if label),
            sample_size=len(labels),
            baseline_rate=baseline_rate,
            min_sample_size=min_sample_size,
            significance_level=significance_level,
        )
        existing = (
            session.query(DiscoveredPattern)
            .filter_by(
                condition_type="signal_present",
                condition_description=signal_name,
                evaluation_horizon_days=evaluation_horizon_days,
            )
            .one_or_none()
        )
        if not result.significant and existing is None:
            continue  # never discovered, still not significant -- nothing to record
        row = _upsert_pattern(session, "signal_present", signal_name, evaluation_horizon_days, result, now)
        updated_rows.append(row)

    session.commit()
    return updated_rows
