"""CouncilEngine: runs every registered, non-DISABLED expert for one
council against a caller-supplied symbol and set of engine result
envelopes.

Structurally identical to CompositeIntelligenceEngine.analyze()'s
per-item failure-isolation loop (src/analysis/composite/
composite_intelligence_engine.py, M2.4.1) -- deliberately copied, not
factored into a shared base class, because the two loops operate on
different item types (CompositeFactorSpec vs. ExpertSpec) and a forced
shared abstraction would itself be "modifying existing code merely to
force symmetry," already rejected elsewhere in this codebase.

Every registered expert is expected, by convention, to never raise --
returning completeness=INSUFFICIENT on undefined input instead (see
ExpertResult's own docstring). analyze() additionally enforces this at
the engine level: an expert that violates the convention and raises
anyway is isolated rather than allowed to crash the whole council, and
an expert whose result violates its own numeric bounds (NaN/Infinity/
out-of-range normalized_score or confidence) is isolated identically --
malformed output is treated exactly like a raised exception, never
silently passed through.

Deliberately never blends its experts into one verdict: CouncilResult
exposes the full, unreduced per-expert map (see CouncilResult's own
docstring in types.py). Weighting and synthesis across experts is a
future Signal Engine's job, applied uniformly across every engine/
council source it consumes -- not something CouncilEngine partially
pre-empts for Technical Council alone.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertRegistry, ExpertSpec
from src.analysis.experts.types import Council, CouncilResult, ExpertDirection, ExpertResult, ExpertStatus

logger = logging.getLogger(__name__)


def _validate_bounds(result: ExpertResult) -> None:
    """Raises ValueError if `result` violates its own documented
    numeric contract -- caught by analyze()'s isolation try/except
    exactly like a genuine exception from spec.compute() would be."""
    score = result.normalized_score
    if score is not None:
        if math.isnan(score) or math.isinf(score):
            raise ValueError(f"normalized_score is not finite: {score!r}")
        if not (-1.0 <= score <= 1.0):
            raise ValueError(f"normalized_score out of bounds [-1, 1]: {score!r}")

    confidence = result.confidence
    if math.isnan(confidence) or math.isinf(confidence):
        raise ValueError(f"confidence is not finite: {confidence!r}")
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence out of bounds [0, 1]: {confidence!r}")


def _insufficient_result(spec: ExpertSpec, symbol: str, exc: Exception) -> ExpertResult:
    return ExpertResult(
        expert_id=spec.expert_id,
        expert_name=spec.name,
        council=spec.council,
        domain=spec.domain,
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        direction=ExpertDirection.NEUTRAL,
        normalized_score=None,
        confidence=0.0,
        completeness=DataCompleteness.INSUFFICIENT,
        freshness=Freshness.UNKNOWN,
        evidence=(),
        contributing_metrics=tuple(spec.contributing_metrics),
        rule_ids=(),
        warnings=(f"expert raised or produced malformed output during compute(): {exc}",),
        conflicts=(),
        limitations=(),
        version=spec.version,
        metadata={"error_type": type(exc).__name__, "error_message": str(exc)},
    )


class CouncilEngine:
    """Runs every registered expert for one council (default registry:
    the full BEIF expert set) against one symbol's already-computed
    engine result envelopes.

    By default, only PRODUCTION and VALIDATED experts contribute to
    analyze()'s result -- PROPOSED/EXPERIMENTAL/SHADOW experts are
    reachable via the registry (for reachability tests, BEIF Section 8)
    but excluded from the council's real output, and DISABLED experts
    are skipped entirely. Pass include_all_statuses=True for the
    shadow-mode/debug mode BEIF Section 15 describes, which computes
    every non-DISABLED expert regardless of promotion status.
    """

    _DEFAULT_VISIBLE_STATUSES = (ExpertStatus.PRODUCTION, ExpertStatus.VALIDATED)

    def __init__(self, council: Council, registry: ExpertRegistry = DEFAULT_EXPERT_REGISTRY):
        self._council = council
        self._registry = registry

    def analyze(
        self,
        symbol: str,
        envelopes: Dict[str, EngineResultEnvelope],
        include_all_statuses: bool = False,
    ) -> CouncilResult:
        computed: Dict[str, ExpertResult] = {}
        for spec in self._registry.specs_for_council(self._council):
            if spec.status is ExpertStatus.DISABLED:
                continue
            if not include_all_statuses and spec.status not in self._DEFAULT_VISIBLE_STATUSES:
                continue
            try:
                result = spec.compute(symbol, envelopes)
                _validate_bounds(result)
            except Exception as exc:
                logger.error(
                    "Expert '%s' raised or produced malformed output during compute(); "
                    "isolating it as INSUFFICIENT: %s",
                    spec.expert_id,
                    exc,
                    exc_info=True,
                )
                result = _insufficient_result(spec, symbol, exc)
            computed[spec.expert_id] = result

        return CouncilResult(council=self._council, experts=computed)
