"""The expert registry: the extension point future councils use to
discover every expert, without modifying any existing expert.

Mirrors CompositeFactorRegistry's shape (src/analysis/composite/
registry.py, M2.4) deliberately -- a fourth, completely independent
registry: none of IndicatorRegistry, RatioRegistry,
CompositeFactorRegistry, or this one import each other.

Unlike CompositeFactorRegistry (a flat list, since M2.4 shipped a
single, undivided factor set), this registry partitions its specs by
Council so that CouncilEngine (council_engine.py) never has to filter
the full set itself and so a future council can be queried in
isolation without importing anything about a sibling council's
experts.

An expert's compute function takes the symbol being analyzed plus the
already-computed engine result envelopes for that symbol -- unlike
CompositeFactorSpec.compute, which takes only envelopes.
ExpertResult (types.py) requires a `symbol` field that no envelope
carries (EngineResultEnvelope has no symbol field, matching
CompositeFactorOutput's own precedent of not carrying one either) --
so the compute signature must receive it explicitly. This is a small,
mechanical, disclosed completion of the BEIF specification, not a
reopening of it: BEIF Section 4 requires `symbol` on ExpertResult,
and no other already-approved contract supplies it.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List

from src.analysis.composite.types import EngineResultEnvelope
from src.analysis.experts.types import Council, ExpertResult, ExpertStatus

ExpertComputeFn = Callable[[str, Dict[str, EngineResultEnvelope]], ExpertResult]


@dataclass(frozen=True)
class ExpertSpec:
    expert_id: str
    name: str
    council: Council
    domain: str
    version: str
    status: ExpertStatus
    required_engines: List[str]
    contributing_metrics: List[str]
    supported_markets: List[str]
    supported_timeframes: List[str]
    execution_priority: int
    compute: ExpertComputeFn


class ExpertRegistry:
    """A named collection of ExpertSpecs, keyed by expert_id.
    CouncilEngine iterates specs_for_council(); it never hardcodes
    expert names."""

    def __init__(self) -> None:
        self._specs: Dict[str, ExpertSpec] = {}

    def register(self, spec: ExpertSpec) -> None:
        if spec.expert_id in self._specs:
            raise ValueError(f"An expert named {spec.expert_id!r} is already registered")
        self._specs[spec.expert_id] = spec

    def get(self, expert_id: str) -> ExpertSpec:
        return self._specs[expert_id]

    def all_specs(self) -> List[ExpertSpec]:
        return list(self._specs.values())

    def specs_for_council(self, council: Council) -> List[ExpertSpec]:
        return [spec for spec in self._specs.values() if spec.council is council]


DEFAULT_EXPERT_REGISTRY = ExpertRegistry()
