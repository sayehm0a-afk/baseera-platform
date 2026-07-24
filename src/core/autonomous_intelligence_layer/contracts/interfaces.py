"""The AIL extension points: one `typing.Protocol` per component kind
named in the current instruction (Supervisor AI, Planner AI, Reflection
Engine, Memory Engine, Multi-Agent Collaboration, Debate Engine, Voting
Engine, Knowledge Graph, Self-Improvement Engine), plus one generic
catch-all (`IAutonomousAgent`) for future autonomous agents that don't
fit a named kind.

Structural, not base classes to inherit from -- the same deliberate
choice `src.analysis.core.contracts.AnalysisOutput`/`AnalysisEngineResult`
already made, for the same reason: a future concrete `SupervisorAI`
implementation only needs to have the right shape (the right attribute
and the right method signature), not inherit from anything defined here
or import this module at all. This is what lets a future, separately-
approved milestone write `src/core/autonomous_intelligence_layer/
supervisor_ai/supervisor_ai.py` v2 (or any other concrete component)
without this contracts package needing to change, and what lets these
interfaces be checked (`isinstance(x, ISupervisorAgent)`, since every one
is `@runtime_checkable`) without either side importing the other.

Every method returns `IntelligenceComponentOutput` (or a tuple of them)
-- the one generic envelope defined in `types.py` -- rather than a
bespoke return type per interface. This is a deliberate scope boundary:
designing what a `Plan`, a `Reflection`, a debate transcript, or a
knowledge-graph query result actually *contains* is real design work for
whichever future milestone implements that specific component, not
something to invent here as a "placeholder" shape. What this module
fixes is only the calling convention -- method name, argument shape,
return envelope -- exactly the "extension point," nothing about the
component's internal behavior.

None of these interfaces are implemented anywhere in this codebase. No
class in this repository currently satisfies any of them, and this
module does not assert otherwise -- see `tests/unit/core/
autonomous_intelligence_layer/contracts/test_interfaces.py` for the
minimal, test-only fake classes used to prove each Protocol is actually
satisfiable (not vacuous), which are not shipped as, and must never be
mistaken for, real implementations.
"""

from typing import Any, Mapping, Protocol, Tuple, runtime_checkable

from src.core.autonomous_intelligence_layer.contracts.types import (
    AgentIdentity,
    IntelligenceComponentOutput,
    IntelligenceContext,
)


@runtime_checkable
class ISupervisorAgent(Protocol):
    """Oversees a set of subordinate components and decides what runs,
    in what order, under what constraints. Does not itself plan, debate,
    vote, or remember -- it delegates to components satisfying the other
    interfaces below."""

    identity: AgentIdentity

    def supervise(self, context: IntelligenceContext) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IPlannerAgent(Protocol):
    """Decomposes a goal into a plan. What a "plan" is made of (steps,
    a DAG, a simple ordered list) is intentionally undefined here --
    that shape lives in the returned `IntelligenceComponentOutput.payload`,
    owned by whichever concrete planner produces it."""

    identity: AgentIdentity

    def plan(self, goal: str, context: IntelligenceContext) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IReflectionEngine(Protocol):
    """Reviews past outcomes (via `IntelligenceContext.history`) and
    produces an assessment -- gaps, inconsistencies, recommendations.
    Read-only with respect to the history it reviews: this interface has
    no method that mutates a past outcome, only one that reports on it."""

    identity: AgentIdentity

    def reflect(self, context: IntelligenceContext) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IMemoryEngine(Protocol):
    """Stores and retrieves `IntelligenceComponentOutput`s across time.
    `remember` takes ownership of persisting one; `recall` takes an
    unconstrained query shape (`Mapping[str, Any]`, via the `query`
    argument) since what's queryable is a property of the concrete
    memory store, not of this interface."""

    identity: AgentIdentity

    def remember(self, entry: IntelligenceComponentOutput) -> None:
        ...

    def recall(self, query: Mapping[str, Any]) -> Tuple[IntelligenceComponentOutput, ...]:
        ...


@runtime_checkable
class ICollaborationCoordinator(Protocol):
    """Multi-Agent Collaboration's extension point: coordinates a set of
    participants (identified only by `AgentIdentity`, never by a
    concrete component type, so this interface never has to know what
    kind of component it is coordinating) toward one combined output."""

    identity: AgentIdentity

    def coordinate(
        self, participants: Tuple[AgentIdentity, ...], context: IntelligenceContext
    ) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IDebateEngine(Protocol):
    """Runs a structured, multi-perspective argument over one
    proposition among a set of participants and reports the outcome.
    Deliberately does not itself decide who "won" -- that judgment, if
    any, is `payload` content a concrete debate engine defines, not a
    behavior this interface prescribes."""

    identity: AgentIdentity

    def debate(
        self, proposition: str, participants: Tuple[AgentIdentity, ...], context: IntelligenceContext
    ) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IVotingEngine(Protocol):
    """Aggregates opinions from a set of participants over a set of
    proposals into one outcome. Both `proposals` and the aggregation
    rule (majority, weighted, ranked-choice, ...) are left to the
    concrete implementation; this interface only fixes that a vote takes
    proposals and participants and returns one combined
    `IntelligenceComponentOutput`."""

    identity: AgentIdentity

    def vote(
        self, proposals: Tuple[Mapping[str, Any], ...], participants: Tuple[AgentIdentity, ...]
    ) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IKnowledgeGraph(Protocol):
    """Stores and queries structured facts. `upsert`/`query` both use
    the same unconstrained `Mapping[str, Any]` shape the rest of this
    module uses for anything whose internal schema is a future,
    component-owned design decision -- entities, relationships, and
    attributes are exactly that kind of decision, deliberately not made
    here."""

    identity: AgentIdentity

    def query(self, query: Mapping[str, Any]) -> IntelligenceComponentOutput:
        ...

    def upsert(self, facts: Tuple[Mapping[str, Any], ...]) -> None:
        ...


@runtime_checkable
class ISelfImprovementEngine(Protocol):
    """Reviews a history of past `IntelligenceComponentOutput`s (from
    any component kind) and proposes an adjustment. What "adjustment"
    means -- a parameter change, a re-weighting, a prompt edit -- is
    payload content the concrete engine defines; this interface only
    fixes that self-improvement is a function of observed history, never
    of live production data it wasn't shown."""

    identity: AgentIdentity

    def evaluate(self, history: Tuple[IntelligenceComponentOutput, ...]) -> IntelligenceComponentOutput:
        ...


@runtime_checkable
class IAutonomousAgent(Protocol):
    """The generic extension point for any future autonomous agent that
    doesn't fit one of the nine named interfaces above. A component
    satisfying only this interface is still fully registrable (see
    `registry.py`) and fully structurally checkable -- nothing about the
    registry or the other interfaces needs to change to accommodate it."""

    identity: AgentIdentity

    def act(self, context: IntelligenceContext) -> IntelligenceComponentOutput:
        ...
