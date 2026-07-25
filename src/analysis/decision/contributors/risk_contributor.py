"""RiskScoreContributor: the AI Decision Intelligence Layer's risk
leg.

Scores two volatility measures TechnicalAnalysisEngine already
computes but that no existing contributor scores at all: ATR(14)
relative to price (TechnicalScoreContributor never reads `atr_14`),
and Bollinger Band width relative to price (TechnicalScoreContributor
only reports width *trend* as a zero-impact informational signal,
never a score). Nothing here duplicates a point contribution another
contributor already made.

Sign convention -- deliberately the mirror of every other contributor:
a *positive* score here means *low* risk (favorable to conviction), a
*negative* score means elevated risk (unfavorable). This is an
explicit, risk-averse design choice matching how the platform's
example decision breakdown shows "Risk: -6" pulling the total score
down -- elevated volatility is treated as inherently reducing
conviction, independent of direction. The same underlying ATR/
Bollinger measurements also drive `InvestmentDecision.risk_level`
directly (see ai_decision_engine.py), so risk is never silently
folded into the score alone -- it is always visible as its own field.
"""

from typing import Optional, Tuple

from src.analysis.decision.contributors._series_utils import latest_value
from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult

_CORE_SIGNAL_SLOTS = 2


def _price_reference(context: AnalysisContext, result: TechnicalAnalysisResult) -> Optional[float]:
    """Prefers a real, live quote price; falls back to Bollinger's
    middle band (~SMA(20)) as a reasonable price proxy when no live
    quote is available, since ATR-to-price only needs an approximate
    current price level, not settlement-grade precision."""
    if context.latest_price is not None:
        return context.latest_price
    bollinger_latest = result.indicators["bollinger"].latest()
    return bollinger_latest.get("middle") if bollinger_latest else None


def _score_atr_ratio(atr_value: Optional[float], price: Optional[float]) -> Optional[Tuple[float, Signal]]:
    if atr_value is None or price is None or price == 0:
        return None

    ratio = atr_value / price
    if ratio >= 0.03:
        return -8.0, Signal(
            name="atr_volatility",
            description=f"ATR(14) is {ratio:.1%} of price -- elevated volatility increases risk.",
            direction=SignalDirection.BEARISH, source="risk", impact=-8.0,
        )
    if ratio <= 0.012:
        return 4.0, Signal(
            name="atr_volatility",
            description=f"ATR(14) is {ratio:.1%} of price -- low volatility, more stable price action.",
            direction=SignalDirection.BULLISH, source="risk", impact=4.0,
        )
    return 0.0, Signal(
        name="atr_volatility",
        description=f"ATR(14) is {ratio:.1%} of price -- moderate volatility.",
        direction=SignalDirection.NEUTRAL, source="risk", impact=0.0,
    )


def _score_bollinger_width(result: TechnicalAnalysisResult) -> Optional[Tuple[float, Signal]]:
    upper = latest_value(result.bollinger.upper)
    lower = latest_value(result.bollinger.lower)
    middle = latest_value(result.bollinger.middle)
    if upper is None or lower is None or middle is None or middle == 0:
        return None

    width_ratio = (upper - lower) / middle
    if width_ratio >= 0.10:
        return -6.0, Signal(
            name="bollinger_band_risk",
            description=f"Bollinger Band width is {width_ratio:.1%} of price -- wide bands signal elevated risk.",
            direction=SignalDirection.BEARISH, source="risk", impact=-6.0,
        )
    if width_ratio <= 0.04:
        return 3.0, Signal(
            name="bollinger_band_risk",
            description=f"Bollinger Band width is {width_ratio:.1%} of price -- narrow bands, lower near-term risk.",
            direction=SignalDirection.BULLISH, source="risk", impact=3.0,
        )
    return 0.0, Signal(
        name="bollinger_band_risk",
        description=f"Bollinger Band width is {width_ratio:.1%} of price -- moderate.",
        direction=SignalDirection.NEUTRAL, source="risk", impact=0.0,
    )


class RiskScoreContributor:
    """The risk leg of the AI Decision Intelligence Layer's
    contributor set."""

    name = "risk"

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

        price = _price_reference(context, result)
        atr_value = result.indicators["atr_14"].latest()
        outcome = _score_atr_ratio(atr_value, price)
        if outcome is not None:
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        outcome = _score_bollinger_width(result)
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
