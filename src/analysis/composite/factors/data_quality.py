"""data_quality_summary: reports aggregate freshness across whichever
engine results were actually supplied to a given
CompositeIntelligenceEngine.analyze() call.

Requires no specific engine -- it reflects on whatever it's given,
which is exactly why it's the one composite factor a future Confidence
Scoring layer will want first.
"""

from typing import Dict

from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY, CompositeFactorSpec
from src.analysis.composite.types import (
    CompositeCategory,
    CompositeFactorOutput,
    DataCompleteness,
    EngineResultEnvelope,
    Freshness,
)


def compute_data_quality_summary(envelopes: Dict[str, EngineResultEnvelope]) -> CompositeFactorOutput:
    total = len(envelopes)
    if total == 0:
        return CompositeFactorOutput(
            name="data_quality_summary",
            category=CompositeCategory.DATA_QUALITY,
            value=None,
            completeness=DataCompleteness.INSUFFICIENT,
            agreement=None,
            contributing_engines=[],
            explanation={"reason": "no engine results supplied"},
        )

    fresh_count = sum(1 for envelope in envelopes.values() if envelope.freshness == Freshness.FRESH)
    value = fresh_count / total

    return CompositeFactorOutput(
        name="data_quality_summary",
        category=CompositeCategory.DATA_QUALITY,
        value=value,
        completeness=DataCompleteness.COMPLETE,
        agreement=None,
        contributing_engines=sorted(envelopes.keys()),
        explanation={
            "rule": "fraction_of_engines_fresh",
            "total_engines": total,
            "fresh_count": fresh_count,
            "freshness_by_engine": {
                name: envelope.freshness.value for name, envelope in envelopes.items()
            },
        },
    )


DEFAULT_COMPOSITE_REGISTRY.register(
    CompositeFactorSpec(
        name="data_quality_summary",
        category=CompositeCategory.DATA_QUALITY,
        required_engines=[],
        compute=compute_data_quality_summary,
    )
)
