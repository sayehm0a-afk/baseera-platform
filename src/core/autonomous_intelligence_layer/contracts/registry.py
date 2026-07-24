"""The AIL component registry: the extension point a future concrete
Supervisor/Planner/Reflection/Memory/Collaboration/Debate/Voting/
Knowledge-Graph/Self-Improvement/custom component would register into,
mirroring `src.analysis.experts.registry.ExpertRegistry`'s shape exactly
-- a fifth independent registry pattern in this codebase (after
`IndicatorRegistry`, `RatioRegistry`, `CompositeFactorRegistry`,
`ExpertRegistry`), none of which import each other.

`DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY` below is deliberately created
empty and stays empty: this module registers nothing, and nothing else
in the production codebase registers anything into it either -- there is
no composition root (no `bootstrap.py`) for this package, unlike every
other registry in this codebase, and that absence is intentional, not an
oversight. See this package's `__init__.py` for why building one now
would cross from "extension point" into "implementation," and
`tests/integration/test_ail_contracts_non_reachability.py` for the
regression test proving `import main` does not populate, import, or
otherwise touch this registry.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List

from src.core.autonomous_intelligence_layer.contracts.types import ComponentKind, ComponentLifecycleStatus

# A factory returns anything structurally satisfying the ComponentKind-
# appropriate interface in interfaces.py (ISupervisorAgent for
# kind=SUPERVISOR, and so on) -- typed loosely here (no return type
# fixed) for the same reason ExpertSpec.compute is typed to a fixed
# signature but AnalysisOutput.category is typed Any: which interface a
# given spec's factory must satisfy is determined by its `kind`, not by
# a type this registry itself can express without importing every
# interface and switching on kind, which would make adding interface
# #11 a change to this file -- exactly the coupling `Council`/
# `ExpertRegistry.specs_for_council` avoids for BEIF.
ComponentFactory = Callable[[], object]


@dataclass(frozen=True)
class IntelligenceComponentSpec:
    component_id: str
    name: str
    kind: ComponentKind
    version: str
    status: ComponentLifecycleStatus
    description: str
    factory: ComponentFactory


class IntelligenceComponentRegistry:
    """A named collection of IntelligenceComponentSpecs, keyed by
    component_id. A future orchestrator (deliberately not built in this
    pass) would iterate `specs_for_kind()`; it would never hardcode
    component names, the same discipline `CouncilEngine` already
    observes for experts."""

    def __init__(self) -> None:
        self._specs: Dict[str, IntelligenceComponentSpec] = {}

    def register(self, spec: IntelligenceComponentSpec) -> None:
        if spec.component_id in self._specs:
            raise ValueError(f"An intelligence component named {spec.component_id!r} is already registered")
        self._specs[spec.component_id] = spec

    def get(self, component_id: str) -> IntelligenceComponentSpec:
        return self._specs[component_id]

    def all_specs(self) -> List[IntelligenceComponentSpec]:
        return list(self._specs.values())

    def specs_for_kind(self, kind: ComponentKind) -> List[IntelligenceComponentSpec]:
        return [spec for spec in self._specs.values() if spec.kind is kind]


DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY = IntelligenceComponentRegistry()
