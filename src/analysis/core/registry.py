"""The engine-level registry: a catalog of every analysis engine that
exists, one level above each engine's own indicator/ratio-level
registry (src/analysis/registry.py for Technical, src/analysis/
fundamental/registry.py for Fundamental).

Deliberately does not standardize each engine's `analyze()` call
signature -- OHLCV DataFrames and financial-statement facts are
genuinely different input shapes, and forcing a common invocation
signature across them would be a premature, leaky abstraction. What
this registry unifies is discovery: a future Composite Analysis
Engine (or Multi-Agent Orchestrator) can enumerate every registered
engine by name and description without importing any of their concrete
modules, and construct an instance via `engine_factory()`. Each
engine's `.analyze()` remains the domain-aware caller's responsibility
to invoke correctly, and each engine's *result* satisfies the shared
AnalysisEngineResult/AnalysisOutput contract in contracts.py.

Nothing in this module imports TechnicalAnalysisEngine or
FundamentalAnalysisEngine -- see bootstrap.py, the one module that
does, for exactly why that split exists.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass(frozen=True)
class EngineSpec:
    name: str
    description: str
    engine_factory: Callable[[], object]


class EngineRegistry:
    """A named collection of EngineSpecs. Adding a future engine (News
    Intelligence, Market Intelligence, Sector Intelligence, Macro
    Analysis, Smart Money/ICT, Wyckoff, or anything else) means
    registering one EngineSpec -- this class never changes."""

    def __init__(self) -> None:
        self._specs: Dict[str, EngineSpec] = {}

    def register(self, spec: EngineSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"An engine named {spec.name!r} is already registered")
        self._specs[spec.name] = spec

    def get(self, name: str) -> EngineSpec:
        return self._specs[name]

    def all_specs(self) -> List[EngineSpec]:
        return list(self._specs.values())


DEFAULT_ENGINE_REGISTRY = EngineRegistry()
