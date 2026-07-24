"""The Decision & Intelligence Modules registry: the extension point a
future concrete Market Scanner/Recommendation Engine/Portfolio
Analyzer/Risk Engine/Alert System/AI Decision Layer would register
into, mirroring `src.analysis.experts.registry.ExpertRegistry` and
`src.core.autonomous_intelligence_layer.contracts.registry.IntelligenceComponentRegistry`'s
shape exactly -- a sixth independent registry pattern in this
codebase, importing none of the other five.

`DEFAULT_INTELLIGENCE_MODULE_REGISTRY` below is deliberately created
empty and stays empty: this module registers nothing, and nothing else
in the production codebase registers anything into it either -- there
is no composition root (no `bootstrap.py`) for this package. See
`integration.py` for why, and
`tests/integration/test_intelligence_contracts_non_reachability.py`
for the regression test proving `import main` does not populate,
import, or otherwise touch this registry.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List


class ModuleKind(str, Enum):
    MARKET_SCANNER = "market_scanner"
    RECOMMENDATION_ENGINE = "recommendation_engine"
    PORTFOLIO_ANALYZER = "portfolio_analyzer"
    RISK_ENGINE = "risk_engine"
    ALERT_SYSTEM = "alert_system"
    AI_DECISION_LAYER = "ai_decision_layer"


# A factory returns anything structurally satisfying the ModuleKind-
# appropriate interface in interfaces.py -- typed loosely for the same
# reason IntelligenceComponentRegistry.ComponentFactory is: which
# interface a given spec's factory must satisfy is determined by its
# `kind`, not by a type this registry itself can express without
# importing every interface and switching on kind.
ModuleFactory = Callable[[], object]


@dataclass(frozen=True)
class IntelligenceModuleSpec:
    module_id: str
    name: str
    kind: ModuleKind
    version: str
    description: str
    factory: ModuleFactory


class IntelligenceModuleRegistry:
    """A named collection of IntelligenceModuleSpecs, keyed by
    module_id. A future orchestrator (deliberately not built in this
    pass) would iterate `specs_for_kind()`; it would never hardcode
    module names, the same discipline `CouncilEngine`/
    `IntelligenceComponentRegistry` already observe."""

    def __init__(self) -> None:
        self._specs: Dict[str, IntelligenceModuleSpec] = {}

    def register(self, spec: IntelligenceModuleSpec) -> None:
        if spec.module_id in self._specs:
            raise ValueError(f"An intelligence module named {spec.module_id!r} is already registered")
        self._specs[spec.module_id] = spec

    def get(self, module_id: str) -> IntelligenceModuleSpec:
        return self._specs[module_id]

    def all_specs(self) -> List[IntelligenceModuleSpec]:
        return list(self._specs.values())

    def specs_for_kind(self, kind: ModuleKind) -> List[IntelligenceModuleSpec]:
        return [spec for spec in self._specs.values() if spec.kind is kind]


DEFAULT_INTELLIGENCE_MODULE_REGISTRY = IntelligenceModuleRegistry()
