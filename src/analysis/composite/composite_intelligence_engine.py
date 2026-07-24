"""CompositeIntelligenceEngine: the single entry point for fusing
already-computed results from independent analysis engines into one
CompositeResult.

Deliberately does not call TechnicalAnalysisEngine/FundamentalAnalysisEngine
itself, and does not load OHLCV bars or financial-statement facts --
running each source engine with its own domain-specific data remains
the caller's responsibility (see the integration test for the expected
usage). This keeps CompositeIntelligenceEngine's only dependency the
structural AnalysisEngineResult/AnalysisOutput contract in
src.analysis.core.contracts, and keeps Technical/Fundamental analysis
completely independent of one another and of this engine.
"""

import logging
from typing import Dict

from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY, CompositeFactorRegistry
from src.analysis.composite.types import (
    CompositeFactorMap,
    CompositeFactorOutput,
    CompositeResult,
    DataCompleteness,
    EngineResultEnvelope,
)

logger = logging.getLogger(__name__)


class CompositeIntelligenceEngine:
    """Runs every factor in a registry (default: the full M2.4 set)
    against a caller-supplied set of engine result envelopes.

    Every registered factor is expected, by convention, to never raise
    -- returning value=None/DataCompleteness.INSUFFICIENT on undefined
    input instead (see CompositeFactorOutput's own docstring). analyze()
    additionally enforces this at the engine level: a factor that
    violates the convention and raises anyway is isolated rather than
    allowed to crash the whole computation, so that one broken factor
    (a bug in a future third-party factor, an unexpected input shape)
    never prevents every other, unrelated factor from still being
    evaluated. This mirrors the same failure-isolation discipline
    ingest_ohlcv/ingest_fundamentals already apply per-symbol.
    """

    def __init__(self, registry: CompositeFactorRegistry = DEFAULT_COMPOSITE_REGISTRY):
        self._registry = registry

    def analyze(self, envelopes: Dict[str, EngineResultEnvelope]) -> CompositeResult:
        computed: CompositeFactorMap = {}
        for spec in self._registry.all_specs():
            try:
                computed[spec.name] = spec.compute(envelopes)
            except Exception as exc:
                logger.error(
                    "Composite factor '%s' raised during compute(); isolating it as INSUFFICIENT: %s",
                    spec.name,
                    exc,
                    exc_info=True,
                )
                computed[spec.name] = CompositeFactorOutput(
                    name=spec.name,
                    category=spec.category,
                    value=None,
                    completeness=DataCompleteness.INSUFFICIENT,
                    agreement=None,
                    contributing_engines=[],
                    explanation={
                        "reason": "factor raised an exception during compute()",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )

        return CompositeResult(factors=computed)
