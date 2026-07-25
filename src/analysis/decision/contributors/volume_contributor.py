"""VolumeScoreContributor: the AI Decision Intelligence Layer's volume
leg.

Reads the same OBV/volume_sma_20 series TechnicalScoreContributor
reads, but derives different facts from them. TechnicalScoreContributor
only checks whether OBV/volume_sma_20 are higher or lower than they
were a few bars ago (a simple up/down trend check). This module checks
whether that flow is *accelerating* -- OBV's own rate of change
speeding up or slowing down -- and whether the latest volume average
represents a *surge* relative to its own recent baseline, two distinct
facts neither of which TechnicalScoreContributor's point total already
counts.
"""

from typing import Optional, Tuple

import pandas as pd

from src.analysis.decision.contributors._series_utils import latest_value, nth_back_value
from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult

_CORE_SIGNAL_SLOTS = 2
_ACCELERATION_STEP = 5
_SURGE_BASELINE_WINDOW = 10


def _score_obv_acceleration(obv_series: pd.Series) -> Optional[Tuple[float, Signal]]:
    current = latest_value(obv_series)
    mid = nth_back_value(obv_series, _ACCELERATION_STEP)
    earliest = nth_back_value(obv_series, _ACCELERATION_STEP * 2)
    if current is None or mid is None or earliest is None:
        return None

    recent_change = current - mid
    prior_change = mid - earliest

    if recent_change > prior_change and recent_change > 0:
        return 10.0, Signal(
            name="obv_acceleration",
            description="On-Balance Volume's recent rise is accelerating -- buying pressure is building.",
            direction=SignalDirection.BULLISH, source="volume", impact=10.0,
        )
    if recent_change < prior_change and recent_change < 0:
        return -10.0, Signal(
            name="obv_acceleration",
            description="On-Balance Volume's recent decline is accelerating -- selling pressure is building.",
            direction=SignalDirection.BEARISH, source="volume", impact=-10.0,
        )
    return 0.0, Signal(
        name="obv_acceleration",
        description="On-Balance Volume flow is not clearly accelerating in either direction.",
        direction=SignalDirection.NEUTRAL, source="volume", impact=0.0,
    )


def _score_volume_surge(volume_sma_series: pd.Series) -> Optional[Tuple[float, Signal]]:
    non_null = volume_sma_series.dropna()
    if len(non_null) <= _SURGE_BASELINE_WINDOW:
        return None

    current = non_null.iloc[-1]
    baseline_window = non_null.iloc[-1 - _SURGE_BASELINE_WINDOW : -1]
    baseline = baseline_window.mean()
    if baseline == 0 or pd.isna(baseline):
        return None

    change = (current - baseline) / baseline
    if change >= 0.15:
        return 8.0, Signal(
            name="volume_surge",
            description=f"20-period average volume is {change:.0%} above its own recent baseline -- a volume surge.",
            direction=SignalDirection.BULLISH, source="volume", impact=8.0,
        )
    if change <= -0.15:
        return -8.0, Signal(
            name="volume_surge",
            description=f"20-period average volume is {abs(change):.0%} below its own recent baseline -- fading interest.",
            direction=SignalDirection.BEARISH, source="volume", impact=-8.0,
        )
    return 0.0, Signal(
        name="volume_surge",
        description="20-period average volume is close to its own recent baseline -- no surge.",
        direction=SignalDirection.NEUTRAL, source="volume", impact=0.0,
    )


class VolumeScoreContributor:
    """The volume leg of the AI Decision Intelligence Layer's
    contributor set."""

    name = "volume"

    def __init__(self, weight: float = 0.10):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        result: Optional[TechnicalAnalysisResult] = context.technical_result
        if result is None:
            return ScoreContribution(
                source=self.name,
                score=None,
                weight=0.0,
                confidence=0.0,
                signals=[],
                notes="No technical analysis result was available for this symbol.",
            )

        points = 0.0
        signals = []
        computed = 0

        outcome = _score_obv_acceleration(result.obv)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        outcome = _score_volume_surge(result.volume_sma_20)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        score = max(0.0, min(100.0, 50.0 + points))
        confidence = round(100.0 * (computed / _CORE_SIGNAL_SLOTS), 1)

        return ScoreContribution(
            source=self.name,
            score=round(score, 1),
            weight=self.default_weight,
            confidence=confidence,
            signals=signals,
        )
