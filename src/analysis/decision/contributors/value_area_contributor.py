"""ValueAreaScoreContributor: the AI Decision Intelligence Layer's
value-area leg.

Scores two volume-at-price facts TechnicalAnalysisEngine computes but
that no existing contributor reads at all: price relative to VWAP
(vwap_20 indicator -- the rolling volume-weighted "fair value"
benchmark) and price relative to the Volume Profile's point of control
(volume_profile indicator -- the price level with the most approximated
trading activity). VolumeScoreContributor only scores OBV/volume-SMA
*flow*, never a price-vs-value-benchmark comparison, so nothing here
duplicates a point contribution it already made.
"""

from typing import List, Optional, Tuple

from src.analysis.decision.contributors._series_utils import latest_value
from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import VolumeProfileResult

_CORE_SIGNAL_SLOTS = 2
_VWAP_DEVIATION_THRESHOLD = 0.01
_POC_DEVIATION_THRESHOLD = 0.02


def _price_reference(context: AnalysisContext, result: TechnicalAnalysisResult) -> Optional[float]:
    if context.latest_price is not None:
        return context.latest_price
    bollinger_latest = result.indicators["bollinger"].latest()
    return bollinger_latest.get("middle") if bollinger_latest else None


def _score_vwap(price: Optional[float], vwap_value: Optional[float]) -> Optional[Tuple[float, Signal]]:
    if price is None or vwap_value is None or vwap_value <= 0:
        return None

    deviation = (price - vwap_value) / vwap_value
    if deviation >= _VWAP_DEVIATION_THRESHOLD:
        return 6.0, Signal(
            name="vwap_deviation",
            description=(
                f"Price ({price:.2f}) is {deviation:.1%} above its 20-bar VWAP ({vwap_value:.2f}) -- "
                "trading above the recent volume-weighted fair value."
            ),
            direction=SignalDirection.BULLISH, source="value_area", impact=6.0,
        )
    if deviation <= -_VWAP_DEVIATION_THRESHOLD:
        return -6.0, Signal(
            name="vwap_deviation",
            description=(
                f"Price ({price:.2f}) is {abs(deviation):.1%} below its 20-bar VWAP ({vwap_value:.2f}) -- "
                "trading below the recent volume-weighted fair value."
            ),
            direction=SignalDirection.BEARISH, source="value_area", impact=-6.0,
        )
    return 0.0, Signal(
        name="vwap_deviation",
        description="Price is trading close to its 20-bar VWAP.",
        direction=SignalDirection.NEUTRAL, source="value_area", impact=0.0,
    )


def _score_volume_profile(
    price: Optional[float], profile: VolumeProfileResult
) -> Optional[Tuple[float, Signal]]:
    if price is None or profile.point_of_control <= 0:
        return None

    poc = profile.point_of_control
    deviation = (price - poc) / poc
    if deviation >= _POC_DEVIATION_THRESHOLD:
        return 5.0, Signal(
            name="volume_profile_deviation",
            description=(
                f"Price ({price:.2f}) is {deviation:.1%} above the volume profile's point of control "
                f"({poc:.2f}) -- trading above the level of highest recent trading activity."
            ),
            direction=SignalDirection.BULLISH, source="value_area", impact=5.0,
        )
    if deviation <= -_POC_DEVIATION_THRESHOLD:
        return -5.0, Signal(
            name="volume_profile_deviation",
            description=(
                f"Price ({price:.2f}) is {abs(deviation):.1%} below the volume profile's point of control "
                f"({poc:.2f}) -- trading below the level of highest recent trading activity."
            ),
            direction=SignalDirection.BEARISH, source="value_area", impact=-5.0,
        )
    return 0.0, Signal(
        name="volume_profile_deviation",
        description="Price is close to the volume profile's point of control -- a fair-value acceptance zone.",
        direction=SignalDirection.NEUTRAL, source="value_area", impact=0.0,
    )


class ValueAreaScoreContributor:
    """The value-area leg of the AI Decision Intelligence Layer's
    contributor set."""

    name = "value_area"

    def __init__(self, weight: float = 0.07):
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

        outcome = _score_vwap(price, latest_value(result.vwap_20))
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        outcome = _score_volume_profile(price, result.volume_profile)
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
