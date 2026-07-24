"""trend_fundamental_alignment: compares SuperTrend's latest direction
(technical) with revenue growth's sign (fundamental).

Relies only on the AnalysisEngineResult/AnalysisOutput structural
contract (src.analysis.core.contracts) -- never imports
TechnicalAnalysisEngine or FundamentalAnalysisEngine, and never reaches
into a concrete result's fields directly. `.get(name)` is expected to
raise KeyError for an unregistered output name, the convention every
concrete AnalysisEngineResult in this codebase (TechnicalAnalysisResult,
FundamentalAnalysisResult, CompositeResult) already follows.
"""

from typing import Dict, Optional

from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY, CompositeFactorSpec
from src.analysis.composite.types import (
    Agreement,
    CompositeCategory,
    CompositeFactorOutput,
    DataCompleteness,
    EngineResultEnvelope,
)

_TECHNICAL_ENGINE = "technical_analysis"
_FUNDAMENTAL_ENGINE = "fundamental_analysis"
_FACTOR_NAME = "trend_fundamental_alignment"


def _extract_supertrend_direction(envelope: Optional[EngineResultEnvelope]) -> Optional[float]:
    if envelope is None:
        return None
    try:
        latest = envelope.result.get("supertrend").latest()
    except KeyError:
        return None
    if not isinstance(latest, dict):
        return None
    return latest.get("direction")


def _extract_revenue_growth(envelope: Optional[EngineResultEnvelope]) -> Optional[float]:
    if envelope is None:
        return None
    try:
        return envelope.result.get("revenue_growth").latest()
    except KeyError:
        return None


def compute_trend_fundamental_alignment(
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
            category=CompositeCategory.ALIGNMENT,
            value=None,
            completeness=DataCompleteness.INSUFFICIENT,
            agreement=Agreement.UNKNOWN,
            contributing_engines=[],
            explanation={"reason": "neither technical_analysis nor fundamental_analysis result supplied"},
        )

    direction = _extract_supertrend_direction(technical_envelope)
    revenue_growth = _extract_revenue_growth(fundamental_envelope)

    if direction is None or revenue_growth is None:
        return CompositeFactorOutput(
            name=_FACTOR_NAME,
            category=CompositeCategory.ALIGNMENT,
            value=None,
            completeness=DataCompleteness.PARTIAL,
            agreement=Agreement.UNKNOWN,
            contributing_engines=present_engines,
            explanation={
                "reason": "supertrend direction or revenue growth unavailable",
                "technical_analysis.supertrend.direction": direction,
                "fundamental_analysis.revenue_growth": revenue_growth,
            },
        )

    if direction > 0 and revenue_growth > 0:
        value, agreement = 1.0, Agreement.AGREE
    elif direction < 0 and revenue_growth < 0:
        value, agreement = -1.0, Agreement.AGREE
    else:
        value, agreement = 0.0, Agreement.DISAGREE

    return CompositeFactorOutput(
        name=_FACTOR_NAME,
        category=CompositeCategory.ALIGNMENT,
        value=value,
        completeness=DataCompleteness.COMPLETE,
        agreement=agreement,
        contributing_engines=[_TECHNICAL_ENGINE, _FUNDAMENTAL_ENGINE],
        explanation={
            "rule": "sign_agreement",
            "technical_analysis.supertrend.direction": direction,
            "fundamental_analysis.revenue_growth": revenue_growth,
        },
    )


DEFAULT_COMPOSITE_REGISTRY.register(
    CompositeFactorSpec(
        name=_FACTOR_NAME,
        category=CompositeCategory.ALIGNMENT,
        required_engines=[_TECHNICAL_ENGINE, _FUNDAMENTAL_ENGINE],
        compute=compute_trend_fundamental_alignment,
    )
)
