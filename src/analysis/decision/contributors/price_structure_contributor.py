"""PriceStructureScoreContributor: the AI Decision Intelligence Layer's
price-structure leg.

Scores two structural, level-based facts TechnicalAnalysisEngine
computes but that no existing contributor reads at all: proximity to
the nearest swing-pivot support/resistance level (support_resistance
indicator), and proximity to the nearest Fibonacci retracement level
of the current window's dominant swing (fibonacci_retracement
indicator). Neither is a re-scoring of a level any other contributor
already counts -- TechnicalScoreContributor/MomentumScoreContributor/
VolumeScoreContributor never read either indicator.
"""

from typing import List, Optional, Tuple

from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import FibonacciLevels, SupportResistanceLevels

_CORE_SIGNAL_SLOTS = 3
_PROXIMITY_THRESHOLD = 0.015  # 1.5% of price counts as "near" a level


def _price_reference(context: AnalysisContext, result: TechnicalAnalysisResult) -> Optional[float]:
    if context.latest_price is not None:
        return context.latest_price
    bollinger_latest = result.indicators["bollinger"].latest()
    return bollinger_latest.get("middle") if bollinger_latest else None


def _score_resistance_proximity(
    price: Optional[float], levels: SupportResistanceLevels
) -> Optional[Tuple[float, Signal]]:
    if price is None or price <= 0 or not levels.resistance:
        return None

    above = [r for r in levels.resistance if r > price]
    if not above:
        return 8.0, Signal(
            name="resistance_breakout",
            description=f"Price ({price:.2f}) is above every detected resistance level -- a breakout.",
            direction=SignalDirection.BULLISH, source="price_structure", impact=8.0,
        )

    nearest = min(above)
    proximity = (nearest - price) / price
    if proximity <= _PROXIMITY_THRESHOLD:
        return -8.0, Signal(
            name="resistance_proximity",
            description=(
                f"Price is approaching resistance at {nearest:.2f} ({proximity:.1%} away) -- a rejection risk."
            ),
            direction=SignalDirection.BEARISH, source="price_structure", impact=-8.0,
        )
    return 0.0, Signal(
        name="resistance_proximity",
        description=f"Nearest resistance is {nearest:.2f}, well above current price -- no near-term overhead pressure.",
        direction=SignalDirection.NEUTRAL, source="price_structure", impact=0.0,
    )


def _score_support_proximity(
    price: Optional[float], levels: SupportResistanceLevels
) -> Optional[Tuple[float, Signal]]:
    if price is None or price <= 0 or not levels.support:
        return None

    below = [s for s in levels.support if s < price]
    if not below:
        return -8.0, Signal(
            name="support_breakdown",
            description=f"Price ({price:.2f}) is below every detected support level -- a breakdown.",
            direction=SignalDirection.BEARISH, source="price_structure", impact=-8.0,
        )

    nearest = max(below)
    proximity = (price - nearest) / price
    if proximity <= _PROXIMITY_THRESHOLD:
        return 8.0, Signal(
            name="support_proximity",
            description=(
                f"Price is holding just above support at {nearest:.2f} ({proximity:.1%} above) -- "
                "a potential bounce zone."
            ),
            direction=SignalDirection.BULLISH, source="price_structure", impact=8.0,
        )
    return 0.0, Signal(
        name="support_proximity",
        description=f"Nearest support is {nearest:.2f}, well below current price -- no near-term floor pressure.",
        direction=SignalDirection.NEUTRAL, source="price_structure", impact=0.0,
    )


def _score_fibonacci_proximity(price: Optional[float], fib: FibonacciLevels) -> Optional[Tuple[float, Signal]]:
    if price is None or price <= 0 or not fib.levels:
        return None

    nearest_name, nearest_price = min(fib.levels.items(), key=lambda kv: abs(kv[1] - price))
    proximity = abs(price - nearest_price) / price
    if proximity > _PROXIMITY_THRESHOLD:
        return 0.0, Signal(
            name="fibonacci_proximity",
            description=(
                f"Price is not close to any Fibonacci retracement level (nearest is the "
                f"{nearest_name}% level at {nearest_price:.2f})."
            ),
            direction=SignalDirection.NEUTRAL, source="price_structure", impact=0.0,
        )

    # In an uptrend, a level between the swing low and high is read as
    # potential support on a pullback; in a downtrend, the mirrored
    # level is potential resistance on a bounce.
    if fib.is_uptrend:
        return 6.0, Signal(
            name="fibonacci_proximity",
            description=(
                f"Price is near the {nearest_name}% Fibonacci retracement level ({nearest_price:.2f}) "
                "of the recent uptrend -- a potential support/bounce zone."
            ),
            direction=SignalDirection.BULLISH, source="price_structure", impact=6.0,
        )
    return -6.0, Signal(
        name="fibonacci_proximity",
        description=(
            f"Price is near the {nearest_name}% Fibonacci retracement level ({nearest_price:.2f}) "
            "of the recent downtrend -- a potential resistance/rejection zone."
        ),
        direction=SignalDirection.BEARISH, source="price_structure", impact=-6.0,
    )


class PriceStructureScoreContributor:
    """The price-structure leg of the AI Decision Intelligence Layer's
    contributor set."""

    name = "price_structure"

    def __init__(self, weight: float = 0.08):
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

        price = _price_reference(context, result)
        points = 0.0
        signals: List[Signal] = []
        computed = 0

        outcome = _score_resistance_proximity(price, result.support_resistance)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        outcome = _score_support_proximity(price, result.support_resistance)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        outcome = _score_fibonacci_proximity(price, result.fibonacci_retracement)
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
