"""SignalInterpreter: turns the raw `Signal` list inside `Evidence`
into `InterpretedSignals` -- factors grouped by direction, ranked by
strength, plus one bullish/bearish/neutral/unavailable tilt per
contributor category.

Reuses `AIDecisionEngine.CATEGORY_LABELS` rather than redefining the
same source-key-to-display-label mapping -- the one piece of state
this module and `AIDecisionEngine` must agree on.
"""

from src.analysis.analyst.types import Evidence, FactorStrength, InterpretedFactor, InterpretedSignals
from src.analysis.decision.ai_decision_engine import CATEGORY_LABELS
from src.analysis.recommendation.types import Signal, SignalDirection

_STRONG_IMPACT_THRESHOLD = 10.0
_MODERATE_IMPACT_THRESHOLD = 5.0


def _category_label(source: str) -> str:
    return CATEGORY_LABELS.get(source, source.replace("_", " ").title())


def _strength(impact: float) -> FactorStrength:
    magnitude = abs(impact)
    if magnitude >= _STRONG_IMPACT_THRESHOLD:
        return FactorStrength.STRONG
    if magnitude >= _MODERATE_IMPACT_THRESHOLD:
        return FactorStrength.MODERATE
    return FactorStrength.MILD


def _to_factor(signal: Signal) -> InterpretedFactor:
    return InterpretedFactor(
        category=_category_label(signal.source),
        description=signal.description,
        direction=signal.direction,
        strength=_strength(signal.impact),
        impact=signal.impact,
    )


class SignalInterpreter:
    def interpret(self, evidence: Evidence) -> InterpretedSignals:
        factors = [_to_factor(s) for s in evidence.signals]

        bullish = sorted(
            (f for f in factors if f.direction is SignalDirection.BULLISH),
            key=lambda f: abs(f.impact),
            reverse=True,
        )
        bearish = sorted(
            (f for f in factors if f.direction is SignalDirection.BEARISH),
            key=lambda f: abs(f.impact),
            reverse=True,
        )
        neutral = [f for f in factors if f.direction is SignalDirection.NEUTRAL]

        category_tilts = {b.category: _tilt(b) for b in evidence.contributor_breakdown}

        return InterpretedSignals(
            bullish_factors=bullish,
            bearish_factors=bearish,
            neutral_factors=neutral,
            category_tilts=category_tilts,
        )


def _tilt(breakdown) -> str:
    if not breakdown.available:
        return "unavailable"
    if breakdown.points > 0:
        return "bullish"
    if breakdown.points < 0:
        return "bearish"
    return "neutral"
