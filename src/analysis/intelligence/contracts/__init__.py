"""Decision & Intelligence Modules contracts -- architecture only.

Added per explicit instruction, alongside the SAHMK live-data
integration: prepare the architecture for Basirah's future decision
layer -- Live Market Scanner, Recommendation Engine, Portfolio
Analysis, Risk Engine, Alert System, AI Decision Layer -- without
implementing any of them, without placeholder business logic or fake
AI, and without changing any production behavior. "Do not implement
fake AI. Only prepare scalable architecture" (verbatim instruction).

Technical Analysis Engine and Fundamental Analysis Engine are
deliberately **not** re-specified here: both already exist as real,
implemented, production engines
(`src.analysis.technical_analysis_engine`,
`src.analysis.fundamental.fundamental_analysis_engine`), already
satisfy `src.analysis.core.contracts.AnalysisEngineResult`, and are
already reachable from `main.py` via the existing bootstrap chain.
Defining a second, parallel "future" interface for something that
already runs in production would be redundant at best and misleading
at worst -- this package's interfaces consume their output (alongside
`CouncilEngine`'s and, once wired, live SAHMK data) rather than
re-describing it.

What's here
-----------
- `types.py` -- shared value types: `RecommendationVerdict`,
  `TimeHorizon`, `RiskLevel`, `AlertSeverity`, `DataState`, plus the
  envelope dataclasses each interface's methods return
  (`ScanMatch`, `RecommendationOutput`, `PortfolioAnalysisResult`,
  `RiskAssessment`, `AlertEvent`, `DecisionOutput`). Every
  human-facing output type carries a mandatory, non-optional
  disclaimer field (`MANDATORY_DISCLAIMER_AR`/`_EN`) -- "analytical
  output, not a binding financial recommendation, no guaranteed
  profit" -- fixed at the type level so no future concrete
  implementation can construct one of these objects without it.
- `interfaces.py` -- one `typing.Protocol` per module
  (`IMarketScanner`, `IRecommendationEngine`, `IPortfolioAnalyzer`,
  `IRiskEngine`, `IAlertSystem`, `IAIDecisionLayer`).
- `registry.py` -- `IntelligenceModuleRegistry` /
  `DEFAULT_INTELLIGENCE_MODULE_REGISTRY`, the extension point a future
  concrete module registers into. Created empty; nothing populates it.
- `integration.py` -- the integration boundary: how a future module
  receives data from `CouncilEngine`/`CompositeIntelligenceEngine`/
  `SahmkMarketDataProvider`, and an explicit statement of what this
  package deliberately does not build yet (an orchestrator, real
  scanning/recommendation/risk logic, a bootstrap.py).

What's NOT here, on purpose
----------------------------
No scanning logic, no recommendation logic, no risk-scoring logic, no
alert-triggering logic, no decision-fusion logic, no bootstrap.py, and
no import of this package from anywhere reachable in the running
application. `tests/integration/test_intelligence_contracts_non_reachability.py`
is the regression test proving `import main` does not import this
package and that every existing production registry is unchanged by
its existence -- the same guarantee
`src.core.autonomous_intelligence_layer.contracts` (the generic
agent-orchestration contracts added alongside M2.10.5) already
provides for its own, different set of nine interfaces. That package
and this one are deliberately separate: AIL's interfaces
(Supervisor/Planner/Reflection/Memory/Collaboration/Debate/Voting/
Knowledge-Graph/Self-Improvement) are generic agent-orchestration
concerns; this package's six interfaces are specifically the
market-decision pipeline that sits downstream of Council/Composite
output. Neither package imports the other.
"""
