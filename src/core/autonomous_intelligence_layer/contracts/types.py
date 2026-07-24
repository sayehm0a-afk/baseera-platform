"""Shared value types for the Autonomous Intelligence Layer (AIL) contracts.

This package (`src.core.autonomous_intelligence_layer.contracts`) is an
architecture-only extension point, added per explicit instruction: design
the interfaces future autonomous components must satisfy, without
implementing any of them and without changing any production behavior.
See this package's `__init__.py` for the full scope statement and
`integration.py` for how a future concrete component would plug into the
rest of Basirah.

Deliberately generic, mirroring `src.analysis.core.contracts`'s own
philosophy: `AnalysisOutput.category` is typed `Any` because "each engine
owns its own category taxonomy... a shared closed enum... would have to
be edited every time a new engine is added." The same reasoning applies
here even more strongly -- Supervisor AI, Planner AI, Reflection Engine,
Memory Engine, a Debate Engine, a Voting Engine, a Knowledge Graph, a
Self-Improvement Engine, and whatever future autonomous agent comes after
them are ten genuinely different kinds of component with ten different
internal data models we have not designed yet (and must not invent here
-- that would be the "placeholder business logic" this task explicitly
forbids). What *can* be fixed now, safely, is the uniform envelope shape
every one of them will use to identify itself and report its output, and
the vocabulary describing what kind of component it is and what
lifecycle stage it's at -- exactly the two things `Council`/`ExpertStatus`
fix for BEIF, without fixing what any individual expert's evidence looks
like.

`ComponentLifecycleStatus` is a deliberate, disclosed *parallel*
definition to `src.analysis.experts.types.ExpertStatus`, not a reuse of
it -- unlike `Freshness`/`DataCompleteness` (which BEIF's `ExpertResult`
does reuse from `src.analysis.composite.types`, because those two are
genuinely engine-agnostic concepts), `ExpertStatus`'s own docstring ties
it explicitly to BEIF: "Governs default visibility inside
CouncilEngine.analyze()." An AIL component is not a BEIF expert and has
no `CouncilEngine` gating its visibility, so importing that enum here
would borrow BEIF-specific semantics this layer does not actually have.
The two enums are intentionally identical in shape (same seven stages)
because the underlying idea -- "not everything registered is
production-ready" -- is genuinely shared, but they are kept as two
separate types so that BEIF's and AIL's lifecycles can diverge in the
future without either constraining the other.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class ComponentKind(str, Enum):
    """What role a registered AIL component plays. Adding a future kind
    of component means adding one value here -- nothing about
    AgentIdentity, IntelligenceContext, IntelligenceComponentOutput, the
    interfaces in `interfaces.py`, or the registry changes, the same
    "adding one value" extensibility `Council` already gives BEIF."""

    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    REFLECTION = "reflection"
    MEMORY = "memory"
    COLLABORATION = "collaboration"
    DEBATE = "debate"
    VOTING = "voting"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    SELF_IMPROVEMENT = "self_improvement"
    CUSTOM = "custom"  # future autonomous agents that don't fit a named kind above


class ComponentLifecycleStatus(str, Enum):
    """Lifecycle stage of a registered component. Structurally identical
    to `ExpertStatus` on purpose (see module docstring for why it is a
    parallel definition, not a shared import) -- a future
    orchestrator-level engine (deliberately not built in this pass, see
    `integration.py`) would use this the same way `CouncilEngine` uses
    `ExpertStatus`: to decide default visibility, never registry
    reachability."""

    PROPOSED = "proposed"
    EXPERIMENTAL = "experimental"
    SHADOW = "shadow"
    VALIDATED = "validated"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass(frozen=True)
class AgentIdentity:
    """The minimal identity every AIL component carries, regardless of
    kind. `component_id` is the registry key (see registry.py);
    `instance_id` is optional and distinguishes multiple simultaneous
    instances of the same registered component (e.g. two concurrently
    running Debate Engine sessions) -- most components will leave it
    unset."""

    component_id: str
    kind: ComponentKind
    version: str
    instance_id: Optional[str] = None


@dataclass(frozen=True)
class IntelligenceContext:
    """The integration-boundary input: what an AIL component receives
    when it runs, built entirely from data the analysis layer already
    computed. `engine_results` is typed `Mapping[str, Any]` deliberately
    -- each value is structurally an
    `src.analysis.core.contracts.AnalysisEngineResult` (or a
    `src.analysis.experts.types.CouncilResult`, which satisfies that same
    contract), but this module must not import any concrete engine or
    council type to stay usable by every future component without
    modification, the same reasoning `AnalysisOutput.category: Any`
    already documents.

    `history` holds prior `IntelligenceComponentOutput`s a component may
    want as temporal context (e.g. Reflection Engine reviewing past
    Supervisor decisions, Self-Improvement Engine reviewing its own past
    evaluations) -- empty by default; nothing populates it yet.

    See `integration.py` for exactly how a future caller would construct
    one of these from `DEFAULT_ENGINE_REGISTRY`/`DEFAULT_EXPERT_REGISTRY`
    output.
    """

    engine_results: Mapping[str, Any]
    as_of: datetime
    symbol: Optional[str] = None
    history: Tuple["IntelligenceComponentOutput", ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntelligenceComponentOutput:
    """The uniform output envelope every AIL component's interface
    method in `interfaces.py` returns, regardless of kind -- the AIL
    equivalent of `AnalysisOutput`, deliberately generic for the same
    reason: what a Plan, a Reflection, a debate transcript, or a
    knowledge-graph query result actually *contains* is real design work
    for a future, separately-approved milestone to do when it implements
    a concrete component, not something to invent here as a "placeholder"
    shape.

    `payload` is where that future, kind-specific content goes --
    unconstrained here on purpose, exactly as `AnalysisOutput.category`
    is left to each engine. `confidence` is deliberately unconstrained
    too: unlike `ExpertResult.confidence`, which BIIC Article IV.1 pins
    to a specific, rule-based, "never a calibrated probability" meaning,
    AIL components are not BEIF experts and are not bound by BIIC's
    investment-specific confidence discipline -- a future component is
    free to define what its own `confidence` means, or leave it `None`
    if the concept doesn't apply.
    """

    identity: AgentIdentity
    kind: ComponentKind
    produced_at: datetime
    payload: Mapping[str, Any]
    confidence: Optional[float] = None
    explanation: Mapping[str, Any] = field(default_factory=dict)
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentMessage:
    """The generic message envelope for the three interfaces in
    `interfaces.py` that inherently involve more than one component
    talking to each other: `ICollaborationCoordinator`, `IDebateEngine`,
    `IVotingEngine`. `recipients = ()` means broadcast to every
    participant. `payload` is unconstrained for the same reason
    `IntelligenceComponentOutput.payload` is."""

    sender: AgentIdentity
    kind: str
    payload: Mapping[str, Any]
    sent_at: datetime
    recipients: Tuple[AgentIdentity, ...] = ()
