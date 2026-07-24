"""valuation_momentum_context: pairs momentum (technical RSI, 0-100)
with valuation (fundamental P/E) into a plain descriptive value.

Deliberately does not invent a compound formula blending an unbounded
P/E with a bounded 0-100 RSI onto one scale -- that would be exactly
the kind of premature, invented model the approved spec ruled out.
`value` is normalized momentum alone (rsi_14 / 100); P/E is carried in
`explanation` as context for a future consumer to interpret, not
folded into the number itself. `agreement` is None here -- unlike
trend_fundamental_alignment, "agreement" isn't a meaningful concept
for a purely contextual (non-directional) factor.
"""

from typing import Dict, Optional

from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY, CompositeFactorSpec
from src.analysis.composite.types import (
    CompositeCategory,
    CompositeFactorOutput,
    DataCompleteness,
    EngineResultEnvelope,
)

_TECHNICAL_ENGINE = "technical_analysis"
_FUNDAMENTAL_ENGINE = "fundamental_analysis"
_FACTOR_NAME = "valuation_momentum_context"


def _extract_rsi(envelope: Optional[EngineResultEnvelope]) -> Optional[float]:
    if envelope is None:
        return None
    try:
        return envelope.result.get("rsi_14").latest()
    except KeyError:
        return None


def _extract_price_to_earnings(envelope: Optional[EngineResultEnvelope]) -> Optional[float]:
    if envelope is None:
        return None
    try:
        return envelope.result.get("price_to_earnings").latest()
    except KeyError:
        return None


def compute_valuation_momentum_context(
    envelopes: Dict[str, EngineResultEnvelope]
) -> CompositeFactorOutput:
    technical_envelope = envelopes.get(_TECHNICAL_ENGINE)
    fundamental_envelope = envelopes.get(_FUNDAMENTAL_ENGINE)
    present_engines = [
        name
        for name, envelope in (
            (_TECHNICAL_ENGINE, technical_envelope),
            (_FUNDAMENTAL_ENGINE, fundamental_envelope),
        )
        if envelope is not None
    ]

    if not present_engines:
        return CompositeFactorOutput(
            name=_FACTOR_NAME,
            category=CompositeCategory.CONTEXT,
            value=None,
            completeness=DataCompleteness.INSUFFICIENT,
            agreement=None,
            contributing_engines=[],
            explanation={"reason": "neither technical_analysis nor fundamental_analysis result supplied"},
        )

    rsi = _extract_rsi(technical_envelope)
    price_to_earnings = _extract_price_to_earnings(fundamental_envelope)

    if rsi is None or price_to_earnings is None:
        return CompositeFactorOutput(
            name=_FACTOR_NAME,
            category=CompositeCategory.CONTEXT,
            value=None,
            completeness=DataCompleteness.PARTIAL,
            agreement=None,
            contributing_engines=present_engines,
            explanation={
                "reason": "rsi_14 or price_to_earnings unavailable",
                "technical_analysis.rsi_14": rsi,
                "fundamental_analysis.price_to_earnings": price_to_earnings,
            },
        )

    return CompositeFactorOutput(
        name=_FACTOR_NAME,
        category=CompositeCategory.CONTEXT,
        value=rsi / 100.0,
        completeness=DataCompleteness.COMPLETE,
        agreement=None,
        contributing_engines=[_TECHNICAL_ENGINE, _FUNDAMENTAL_ENGINE],
        explanation={
            "rule": "normalized_momentum_with_valuation_context",
            "technical_analysis.rsi_14": rsi,
            "fundamental_analysis.price_to_earnings": price_to_earnings,
        },
    )


DEFAULT_COMPOSITE_REGISTRY.register(
    CompositeFactorSpec(
        name=_FACTOR_NAME,
        category=CompositeCategory.CONTEXT,
        required_engines=[_TECHNICAL_ENGINE, _FUNDAMENTAL_ENGINE],
        compute=compute_valuation_momentum_context,
    )
)
