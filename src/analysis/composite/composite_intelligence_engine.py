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

from typing import Dict

from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY, CompositeFactorRegistry
from src.analysis.composite.types import CompositeFactorMap, CompositeResult, EngineResultEnvelope


class CompositeIntelligenceEngine:
    """Runs every factor in a registry (default: the full M2.4 set)
    against a caller-supplied set of engine result envelopes."""

    def __init__(self, registry: CompositeFactorRegistry = DEFAULT_COMPOSITE_REGISTRY):
        self._registry = registry

    def analyze(self, envelopes: Dict[str, EngineResultEnvelope]) -> CompositeResult:
        computed: CompositeFactorMap = {}
        for spec in self._registry.all_specs():
            computed[spec.name] = spec.compute(envelopes)

        return CompositeResult(factors=computed)
