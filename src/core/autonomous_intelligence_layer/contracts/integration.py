"""The integration boundary between the AIL contracts layer and the rest
of Basirah -- how a future concrete component would receive data, and,
just as importantly, the two things this boundary deliberately does not
do yet.

Direction of dependency
------------------------
AIL components consume the analysis layer; the analysis layer must never
import anything from this package, or from
`src.core.autonomous_intelligence_layer` generally. This is the same
one-way boundary already enforced between, e.g., Composite Intelligence
and the engines it fuses (Composite imports Technical/Fundamental
result-carrying envelopes; neither of those engines imports anything
about Composite). A future AIL component built against these interfaces
would receive its input as an `IntelligenceContext`
(`types.IntelligenceContext`), built from whatever the analysis layer has
already computed and made discoverable via
`src.analysis.core.registry.DEFAULT_ENGINE_REGISTRY` (which today holds
`"technical_analysis"`, `"fundamental_analysis"`, `"composite_analysis"`,
and `"technical_council"`) and, for expert-level detail, via
`src.analysis.experts.registry.DEFAULT_EXPERT_REGISTRY`.
`build_intelligence_context` below is the one constructor this module
provides for that -- pure data-shaping (packaging already-computed
results into the envelope `IntelligenceContext` defines), not a decision
or a rule, the same category of helper `src.analysis.composite.types.
build_envelope` already is for `EngineResultEnvelope`.

What this module deliberately does NOT do
-------------------------------------------
1. **No orchestrator.** There is no `AutonomousEngine`/
   `IntelligenceOrchestrator` here that iterates
   `DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY` and calls `.act()`/
   `.supervise()`/etc. on whatever it finds -- that would be dispatch
   *behavior*, the actual thing the current instruction says not to
   build yet ("No placeholder business logic. No fake implementations.
   Only the architecture and extension points."). `CouncilEngine` is the
   closest existing precedent for what that component would eventually
   look like (generic over `Council`, iterates
   `ExpertRegistry.specs_for_council()`, applies status-gated default
   visibility) -- a future, separately-approved milestone can model an
   AIL orchestrator on it directly once there is at least one real
   component for it to orchestrate.
2. **No bootstrap.py, and nothing imports this package.** Every other
   registry in this codebase (`DEFAULT_ENGINE_REGISTRY`,
   `DEFAULT_EXPERT_REGISTRY`, etc.) has a composition root that `main.py`
   imports, which is precisely what makes that registry non-empty and
   reachable in the running application. This package has no such file
   on purpose: writing one -- even one that registers nothing yet --
   would be the first line of code wiring AIL into the live application,
   which is explicitly out of scope until a future milestone actually
   implements a concrete component. `tests/integration/
   test_ail_contracts_non_reachability.py` is the regression test
   proving `import main` does not import this package, and that
   `DEFAULT_ENGINE_REGISTRY`/`DEFAULT_EXPERT_REGISTRY` are unchanged by
   its existence.
3. **The pre-existing, disconnected implementation modules under this
   same `autonomous_intelligence_layer` package** (`supervisor_ai/`,
   `planner_ai/`, `reflection_engine/`, `memory_reasoning/`,
   `debate_engine/`, `voting_system/`, `knowledge_graph/`,
   `self_optimization/`, `agent_registry/`, `agent_runtime/`, and the
   rest) are not imported, referenced, modified, or extended by this
   `contracts` package in any way. Whether a future milestone rewrites
   one of them to satisfy the matching interface above, replaces it
   entirely, or retires it remains an explicitly open decision -- this
   package takes no position on that question and does not need to for
   the interfaces above to be usable.
"""

from datetime import datetime
from typing import Any, Mapping, Optional, Tuple

from src.core.autonomous_intelligence_layer.contracts.types import IntelligenceComponentOutput, IntelligenceContext


def build_intelligence_context(
    engine_results: Mapping[str, Any],
    as_of: datetime,
    symbol: Optional[str] = None,
    history: Tuple[IntelligenceComponentOutput, ...] = (),
    metadata: Optional[Mapping[str, Any]] = None,
) -> IntelligenceContext:
    """Packages already-computed engine/council results into the
    envelope a future AIL component's interface method would receive.
    Does not fetch, compute, or validate anything -- `engine_results` is
    expected to already be assembled by the caller (e.g. from
    `DEFAULT_ENGINE_REGISTRY`'s engines run against one symbol), exactly
    as `build_envelope`'s caller is expected to have already computed
    the engine result it wraps.
    """
    return IntelligenceContext(
        engine_results=engine_results,
        as_of=as_of,
        symbol=symbol,
        history=history,
        metadata=metadata if metadata is not None else {},
    )
