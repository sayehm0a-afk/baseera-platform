"""MomentumScoreContributor: the AI Decision Intelligence Layer's
momentum leg.

Reads the *same* TechnicalAnalysisResult TechnicalScoreContributor
reads (nothing new is computed by TechnicalAnalysisEngine), but derives
genuinely different facts from it -- not a re-scoring of the same
signal under a new name. TechnicalScoreContributor only looks at each
indicator's *latest level* (is RSI above 70, is the MACD histogram
positive). This module looks at the *rate of change* of those same
series -- is RSI rising or falling over the last few bars, is the MACD
histogram expanding or contracting -- plus ADX's raw trend-strength
magnitude, which no other contributor scores at all (TechnicalScoreContributor
only uses ADX to adjust its own confidence, never its score). Nothing
here duplicates a point contribution TechnicalScoreContributor already
made.
"""

from typing import Optional, Tuple

import pandas as pd

from src.analysis.decision.contributors._series_utils import latest_value, nth_back_value
from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult

_CORE_SIGNAL_SLOTS = 3
_VELOCITY_LOOKBACK = 5


def _score_rsi_velocity(rsi_series: pd.Series) -> Optional[Tuple[float, Signal]]:
    current = latest_value(rsi_series)
    prior = nth_back_value(rsi_series, _VELOCITY_LOOKBACK)
    if current is None or prior is None:
        return None

    delta = current - prior
    if delta >= 5:
        return 10.0, Signal(
            name="rsi_velocity",
            description=(
                f"RSI(14) rose {delta:.1f} points over the last {_VELOCITY_LOOKBACK} bars "
                f"({prior:.1f} -> {current:.1f}) -- bullish momentum is building."
            ),
            direction=SignalDirection.BULLISH, source="momentum", impact=10.0,
        )
    if delta <= -5:
        return -10.0, Signal(
            name="rsi_velocity",
            description=(
                f"RSI(14) fell {abs(delta):.1f} points over the last {_VELOCITY_LOOKBACK} bars "
                f"({prior:.1f} -> {current:.1f}) -- bearish momentum is building."
            ),
            direction=SignalDirection.BEARISH, source="momentum", impact=-10.0,
        )
    return 0.0, Signal(
        name="rsi_velocity",
        description=f"RSI(14) is roughly flat over the last {_VELOCITY_LOOKBACK} bars.",
        direction=SignalDirection.NEUTRAL, source="momentum", impact=0.0,
    )


def _score_macd_acceleration(histogram_series: pd.Series) -> Optional[Tuple[float, Signal]]:
    current = latest_value(histogram_series)
    prior = nth_back_value(histogram_series, _VELOCITY_LOOKBACK)
    if current is None or prior is None:
        return None

    delta = current - prior
    if delta > 0 and current > 0:
        return 10.0, Signal(
            name="macd_acceleration",
            description=f"MACD histogram is expanding positively ({prior:.3f} -> {current:.3f}) -- upward momentum is accelerating.",
            direction=SignalDirection.BULLISH, source="momentum", impact=10.0,
        )
    if delta < 0 and current < 0:
        return -10.0, Signal(
            name="macd_acceleration",
            description=f"MACD histogram is expanding negatively ({prior:.3f} -> {current:.3f}) -- downward momentum is accelerating.",
            direction=SignalDirection.BEARISH, source="momentum", impact=-10.0,
        )
    return 0.0, Signal(
        name="macd_acceleration",
        description="MACD histogram momentum is not clearly accelerating in either direction.",
        direction=SignalDirection.NEUTRAL, source="momentum", impact=0.0,
    )


def _score_trend_strength(adx_value: Optional[float], supertrend_direction: Optional[float]) -> Optional[Tuple[float, Signal]]:
    if adx_value is None or supertrend_direction is None:
        return None

    direction = 1 if supertrend_direction > 0 else (-1 if supertrend_direction < 0 else 0)
    if adx_value >= 25:
        points = 10.0 * direction
        strength = "a strong"
    elif adx_value < 15:
        points = 0.0
        direction = 0
        strength = "no clear"
    else:
        points = 5.0 * direction
        strength = "a moderate"

    trend_direction = f", direction {'bullish' if direction > 0 else 'bearish'}" if direction != 0 else ""
    description = f"ADX(14)={adx_value:.1f} indicates {strength} trend{trend_direction}."
    signal_direction = SignalDirection.BULLISH if points > 0 else (SignalDirection.BEARISH if points < 0 else SignalDirection.NEUTRAL)
    return points, Signal(
        name="trend_strength", description=description, direction=signal_direction, source="momentum", impact=points
    )


class MomentumScoreContributor:
    """The momentum leg of the AI Decision Intelligence Layer's
    contributor set. `default_weight` and everything else about this
    class can be tuned or replaced without AIDecisionEngine or
    RecommendationEngine changing."""

    name = "momentum"

    def __init__(self, weight: float = 0.15):
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

        outcome = _score_rsi_velocity(result.indicators["rsi_14"].value)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        outcome = _score_macd_acceleration(result.macd.histogram)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        adx_value = result.indicators["adx_14"].latest()
        supertrend_latest = result.indicators["supertrend"].latest()
        supertrend_direction = supertrend_latest.get("direction") if supertrend_latest else None
        outcome = _score_trend_strength(adx_value, supertrend_direction)
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
