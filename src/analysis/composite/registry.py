"""The composite factor registry: the extension point future
intelligence layers use to discover every composite factor, without
modifying any existing factor.

Every factor function under src/analysis/composite/factors/ stays a
plain, isolated pure function -- it has zero awareness that a registry
exists. This mirrors src/analysis/registry.py (M2.2) and
src/analysis/fundamental/registry.py (M2.3) exactly, as a third,
completely separate registry: none of the three import each other.

Unlike IndicatorSpec.compute (returns a raw value the engine wraps in
IndicatorOutput) and RatioSpec.compute (returns Optional[float] the
engine wraps in RatioOutput), CompositeFactorSpec.compute returns a
fully-formed CompositeFactorOutput directly. A composite factor fuses
multiple, independently-partial sources, so only the factor function
itself knows its own completeness/agreement/contributing_engines/
explanation -- the engine has nothing meaningful to add by wrapping a
bare value itself, so it doesn't.

Unlike src/analysis/registry.py and src/analysis/fundamental/registry.py
(each a single build_default_registry() importing every indicator/
ratio function centrally, since M2.2/M2.3 shipped their full set in
one milestone), each composite factor module self-registers into
DEFAULT_COMPOSITE_REGISTRY at import time -- the same self-registration
pattern DevMarketDataProvider/DevFundamentalDataProvider already use
for FundamentalDataProviderFactory. This lets factors be added across
independent, atomic commits without this file needing to import a
factor module that doesn't exist yet at commit time.

Adding a future factor -- including one that consumes an engine that
doesn't exist yet (News, Corporate Actions, Market Events, Risk
Assessment) -- means writing one pure function plus one new
CompositeFactorSpec, registered at the bottom of that factor's own
module. CompositeIntelligenceEngine.analyze() and every existing
factor are unaffected.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List

from src.analysis.composite.types import CompositeCategory, CompositeFactorOutput, EngineResultEnvelope

CompositeComputeFn = Callable[[Dict[str, EngineResultEnvelope]], CompositeFactorOutput]


@dataclass(frozen=True)
class CompositeFactorSpec:
    name: str
    category: CompositeCategory
    required_engines: List[str]
    compute: CompositeComputeFn


class CompositeFactorRegistry:
    """A named collection of CompositeFactorSpecs.
    CompositeIntelligenceEngine iterates one of these; it never
    hardcodes factor names."""

    def __init__(self) -> None:
        self._specs: List[CompositeFactorSpec] = []

    def register(self, spec: CompositeFactorSpec) -> None:
        if any(existing.name == spec.name for existing in self._specs):
            raise ValueError(f"A composite factor named {spec.name!r} is already registered")
        self._specs.append(spec)

    def all_specs(self) -> List[CompositeFactorSpec]:
        return list(self._specs)


DEFAULT_COMPOSITE_REGISTRY = CompositeFactorRegistry()
