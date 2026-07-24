"""Proves each Protocol in interfaces.py is actually satisfiable (not
vacuous) via minimal, test-only fake classes -- the same technique
test_types.py's BEIF counterpart
(test_expert_result_satisfies_analysis_output) already uses for
AnalysisOutput/AnalysisEngineResult.

These fakes are not, and must never be mistaken for, real
implementations: each returns a hand-built IntelligenceComponentOutput
with no actual reasoning behind it. Their only job is to prove the
interface shape is implementable by ordinary Python classes with zero
inheritance from anything in this package -- structural typing working
as intended.
"""

from datetime import datetime, timezone

from src.core.autonomous_intelligence_layer.contracts.interfaces import (
    IAutonomousAgent,
    ICollaborationCoordinator,
    IDebateEngine,
    IKnowledgeGraph,
    IMemoryEngine,
    IPlannerAgent,
    IReflectionEngine,
    ISelfImprovementEngine,
    ISupervisorAgent,
    IVotingEngine,
)
from src.core.autonomous_intelligence_layer.contracts.types import (
    AgentIdentity,
    ComponentKind,
    IntelligenceComponentOutput,
    IntelligenceContext,
)


def _identity(kind: ComponentKind) -> AgentIdentity:
    return AgentIdentity(component_id=f"test.{kind.value}", kind=kind, version="0.0.0-test")


def _output(kind: ComponentKind, identity: AgentIdentity) -> IntelligenceComponentOutput:
    return IntelligenceComponentOutput(
        identity=identity, kind=kind, produced_at=datetime.now(timezone.utc), payload={}
    )


def _context() -> IntelligenceContext:
    return IntelligenceContext(engine_results={}, as_of=datetime.now(timezone.utc))


class _FakeSupervisor:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.SUPERVISOR)

    def supervise(self, context: IntelligenceContext) -> IntelligenceComponentOutput:
        return _output(ComponentKind.SUPERVISOR, self.identity)


class _FakePlanner:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.PLANNER)

    def plan(self, goal, context):
        return _output(ComponentKind.PLANNER, self.identity)


class _FakeReflectionEngine:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.REFLECTION)

    def reflect(self, context):
        return _output(ComponentKind.REFLECTION, self.identity)


class _FakeMemoryEngine:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.MEMORY)

    def remember(self, entry):
        return None

    def recall(self, query):
        return ()


class _FakeCollaborationCoordinator:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.COLLABORATION)

    def coordinate(self, participants, context):
        return _output(ComponentKind.COLLABORATION, self.identity)


class _FakeDebateEngine:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.DEBATE)

    def debate(self, proposition, participants, context):
        return _output(ComponentKind.DEBATE, self.identity)


class _FakeVotingEngine:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.VOTING)

    def vote(self, proposals, participants):
        return _output(ComponentKind.VOTING, self.identity)


class _FakeKnowledgeGraph:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.KNOWLEDGE_GRAPH)

    def query(self, query):
        return _output(ComponentKind.KNOWLEDGE_GRAPH, self.identity)

    def upsert(self, facts):
        return None


class _FakeSelfImprovementEngine:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.SELF_IMPROVEMENT)

    def evaluate(self, history):
        return _output(ComponentKind.SELF_IMPROVEMENT, self.identity)


class _FakeAutonomousAgent:
    def __init__(self) -> None:
        self.identity = _identity(ComponentKind.CUSTOM)

    def act(self, context):
        return _output(ComponentKind.CUSTOM, self.identity)


def test_fake_supervisor_satisfies_isupervisoragent():
    assert isinstance(_FakeSupervisor(), ISupervisorAgent)


def test_fake_planner_satisfies_iplanneragent():
    assert isinstance(_FakePlanner(), IPlannerAgent)


def test_fake_reflection_engine_satisfies_ireflectionengine():
    assert isinstance(_FakeReflectionEngine(), IReflectionEngine)


def test_fake_memory_engine_satisfies_imemoryengine():
    assert isinstance(_FakeMemoryEngine(), IMemoryEngine)


def test_fake_collaboration_coordinator_satisfies_icollaborationcoordinator():
    assert isinstance(_FakeCollaborationCoordinator(), ICollaborationCoordinator)


def test_fake_debate_engine_satisfies_idebateengine():
    assert isinstance(_FakeDebateEngine(), IDebateEngine)


def test_fake_voting_engine_satisfies_ivotingengine():
    assert isinstance(_FakeVotingEngine(), IVotingEngine)


def test_fake_knowledge_graph_satisfies_iknowledgegraph():
    assert isinstance(_FakeKnowledgeGraph(), IKnowledgeGraph)


def test_fake_self_improvement_engine_satisfies_iselfimprovementengine():
    assert isinstance(_FakeSelfImprovementEngine(), ISelfImprovementEngine)


def test_fake_autonomous_agent_satisfies_iautonomousagent():
    assert isinstance(_FakeAutonomousAgent(), IAutonomousAgent)


def test_none_of_the_fakes_inherit_from_anything_in_this_package():
    # Structural typing working as intended: every fake above is isinstance-
    # checkable against its interface purely by shape, with zero inheritance.
    for fake_cls in (
        _FakeSupervisor,
        _FakePlanner,
        _FakeReflectionEngine,
        _FakeMemoryEngine,
        _FakeCollaborationCoordinator,
        _FakeDebateEngine,
        _FakeVotingEngine,
        _FakeKnowledgeGraph,
        _FakeSelfImprovementEngine,
        _FakeAutonomousAgent,
    ):
        assert fake_cls.__bases__ == (object,)


def test_a_fake_satisfying_one_interface_does_not_satisfy_an_unrelated_one():
    # ISupervisorAgent requires .supervise(); a bare planner has no such
    # method, so it must not be mistaken for a supervisor.
    assert not isinstance(_FakePlanner(), ISupervisorAgent)
