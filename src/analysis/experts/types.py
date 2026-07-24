"""Shared types for the Basirah Expert Intelligence Framework (BEIF).

Two-level design, mirroring the precedent already proven twice in this
codebase (`IndicatorOutput` -> `TechnicalAnalysisResult`, M2.2;
`CompositeFactorOutput` -> `CompositeResult`, M2.4): `ExpertResult`
satisfies `src.analysis.core.contracts.AnalysisOutput` structurally
(name, category, value, .latest()), and `CouncilResult` satisfies
`AnalysisEngineResult` structurally (.get(), .latest_snapshot()) --
without either importing that module, the same technique every prior
engine-level result type already uses.

An individual expert is deliberately *not* itself an
AnalysisEngineResult -- exactly as a single CompositeFactorOutput is
not registered into DEFAULT_ENGINE_REGISTRY on its own, only the
CouncilResult produced by running an entire council is. This keeps the
engine-level registry from being polluted with dozens of
single-expert entries that are only ever meaningful in aggregate.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

# Reused, not redefined -- BEIF Section 4 requires ExpertResult reuse the
# same Freshness/DataCompleteness vocabulary CompositeFactorOutput (M2.4)
# already established, rather than inventing a second, parallel one.
from src.analysis.composite.types import DataCompleteness, Freshness


class Council(str, Enum):
    """The five BEIF councils. Adding a future council means adding one
    value here plus one new CouncilEngine(council=...) instantiation --
    nothing about ExpertResult/CouncilResult/CouncilEngine changes."""

    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SAUDI_MARKET = "saudi_market"
    RISK = "risk"
    INTELLIGENCE_LEARNING = "intelligence_learning"


class ExpertDirection(str, Enum):
    """Distinct from a future Signal Engine's SignalAction -- an expert
    only ever answers within its own narrow domain, never the
    platform's final action vocabulary."""

    BEARISH = "bearish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"  # domain has no directional opinion, or evidence is too weak to call
    MIXED = "mixed"  # domain's own inputs disagreed with each other


class ExpertStatus(str, Enum):
    """Lifecycle state, per BEIF Section 15. Governs default visibility
    inside CouncilEngine.analyze() -- see that class's docstring --
    never registry reachability, which every status is equally
    entitled to (a DISABLED expert must still be discoverable so
    reachability tests can see it)."""

    PROPOSED = "proposed"
    EXPERIMENTAL = "experimental"
    SHADOW = "shadow"
    VALIDATED = "validated"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass(frozen=True)
class EvidenceItem:
    """One named rule firing on one already-computed metric.

    `metric_name` must name a key actually present on the consumed
    engine result's own output map (e.g. "adx_14") -- this is what
    lets a future registry-level test detect drift if an indicator is
    ever renamed. `contribution` is signed, [-1, 1]: this item's own
    pull on the expert's eventual normalized_score, before combination
    with any other evidence item.
    """

    metric_name: str
    observed_value: Any
    rule_id: str
    contribution: float


@dataclass(frozen=True)
class ExpertResult:
    """Satisfies src.analysis.core.contracts.AnalysisOutput structurally
    -- name, category, value, .latest() -- the same technique
    IndicatorOutput/RatioOutput/CompositeFactorOutput already use.

    Every field is populated even when undefined (None/empty-tuple
    sentinels, never omitted) so every consumer can rely on a stable
    shape -- an expert with INSUFFICIENT completeness still returns a
    full ExpertResult, it does not return nothing.
    """

    expert_id: str
    expert_name: str
    council: Council
    domain: str
    symbol: str
    as_of: datetime
    direction: ExpertDirection
    normalized_score: Optional[float]  # [-1.0, 1.0], None iff completeness is INSUFFICIENT
    confidence: float  # [0.0, 1.0] -- rule-based, never a calibrated probability (BIIC Article IV.1)
    completeness: DataCompleteness
    freshness: Freshness
    evidence: Tuple[EvidenceItem, ...]
    contributing_metrics: Tuple[str, ...]
    rule_ids: Tuple[str, ...]
    warnings: Tuple[str, ...]
    conflicts: Tuple[str, ...]
    limitations: Tuple[str, ...]
    version: str
    metadata: Mapping[str, Any]

    @property
    def name(self) -> str:
        return self.expert_id

    @property
    def category(self) -> Council:
        return self.council

    @property
    def value(self) -> Optional[float]:
        return self.normalized_score

    def latest(self) -> Any:
        return self.normalized_score


ExpertMap = Dict[str, ExpertResult]


@dataclass(frozen=True)
class CouncilResult:
    """Satisfies src.analysis.core.contracts.AnalysisEngineResult
    structurally -- the exact same technique CompositeResult (M2.4)
    already uses. A future Signal Engine can consume this identically
    to how Composite consumes Technical/Fundamental results today.

    Deliberately never reduces its experts to one blended verdict --
    see CouncilEngine's own docstring for why (BEIF Section 6: "no
    simple majority vote masquerading as intelligence").
    """

    council: Council
    experts: ExpertMap

    def get(self, name: str) -> ExpertResult:
        return self.experts[name]

    def latest_snapshot(self) -> Dict[str, Any]:
        return {name: result.latest() for name, result in self.experts.items()}
