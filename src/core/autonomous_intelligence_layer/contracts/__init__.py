"""Autonomous Intelligence Layer (AIL) contracts -- architecture only.

Added per explicit instruction, ahead of M2.11: design the interfaces,
contracts, extension points, and integration boundaries that will let
Basirah eventually support a Supervisor AI, a Planner AI, a Reflection
Engine, a Memory Engine, Multi-Agent Collaboration, a Debate Engine, a
Voting Engine, a Knowledge Graph, a Self-Improvement Engine, and future
autonomous agents -- without implementing any of them, without any
placeholder business logic or fake implementations, and without changing
any production behavior.

What's here
-----------
- `types.py` -- the shared value types every future component uses:
  `ComponentKind`, `ComponentLifecycleStatus`, `AgentIdentity`,
  `IntelligenceContext` (the input envelope), `IntelligenceComponentOutput`
  (the output envelope), `AgentMessage` (for collaboration/debate/voting).
- `interfaces.py` -- one `typing.Protocol` per component kind
  (`ISupervisorAgent`, `IPlannerAgent`, `IReflectionEngine`,
  `IMemoryEngine`, `ICollaborationCoordinator`, `IDebateEngine`,
  `IVotingEngine`, `IKnowledgeGraph`, `ISelfImprovementEngine`) plus one
  generic catch-all (`IAutonomousAgent`) for anything not yet named.
- `registry.py` -- `IntelligenceComponentRegistry` /
  `DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY`, the extension point a future
  concrete component registers into. Created empty; nothing populates it.
- `integration.py` -- the integration boundary: how a future component
  receives data from the existing analysis layer, and an explicit
  statement of the two things this package deliberately does not build
  yet (an orchestrator, and a bootstrap/composition-root wiring it into
  `main.py`).

What's NOT here, on purpose
----------------------------
No orchestration logic, no concrete component, no bootstrap.py, and no
import of this package from anywhere reachable in the running
application. `tests/integration/test_ail_contracts_non_reachability.py`
is the regression test proving that last point holds -- `import main`
produces byte-identical `DEFAULT_ENGINE_REGISTRY`/`DEFAULT_EXPERT_REGISTRY`
contents with or without this package existing.

This package also does not modify, import, or take a position on the
pre-existing, disconnected implementation modules elsewhere under
`src.core.autonomous_intelligence_layer` (`supervisor_ai/`,
`planner_ai/`, `reflection_engine/`, `memory_reasoning/`,
`debate_engine/`, `voting_system/`, `knowledge_graph/`,
`self_optimization/`, `agent_registry/`, `agent_runtime/`, and the rest)
-- see `integration.py` point 3 for why that stays an explicitly open
question for a future milestone.
"""
