"""The integration boundary between this package and the rest of
Basirah -- how a future concrete module would receive data, and, just
as importantly, the things this boundary deliberately does not do yet.

Direction of dependency
------------------------
These six modules consume the analysis and market-data layers; neither
layer imports anything from this package. A future concrete module
built against these interfaces receives its input already computed:

- `IMarketScanner.scan()` would read from whichever
  `IMarketDataProvider` `src.market_data.provider_factory.
  get_configured_provider()` currently selects -- never a hardcoded
  provider -- and is explicitly subject to Phase 5's rate-limit
  discipline: `docs/SAHMK_INTEGRATION.md` and this package's own
  `__init__.py` both flag that scanning the full Saudi market on a
  metered plan needs a request-budget decision made first, which this
  architecture-only pass does not make.
- `IRecommendationEngine.recommend()` receives a
  `src.market_data.models.RecommendationInput` -- already assembled
  from `TechnicalAnalysisEngine`/`FundamentalAnalysisEngine` output
  (via `src.analysis.core.registry.DEFAULT_ENGINE_REGISTRY`),
  `CouncilEngine` output (via
  `src.analysis.experts.registry.DEFAULT_EXPERT_REGISTRY`), and
  optionally a live `MarketQuote`.
- `IPortfolioAnalyzer.analyze()` / `IRiskEngine.assess()` receive
  already-known `PortfolioPosition`s -- this package takes no position
  on where positions are stored (no `Position` domain model or table
  exists yet; that is itself a future, separately-scoped decision).
- `IAlertSystem.evaluate()` would poll already-computed
  quotes/recommendations/risk assessments on some future schedule --
  no scheduler, cron, or background worker is wired here.
- `IAIDecisionLayer.decide()` receives a `DecisionContext` built from
  the other five modules' own output -- it is the fusion point, mirror
  of how `CompositeIntelligenceEngine` sits above Technical/
  Fundamental rather than beside them.

`build_recommendation_input` below is the one constructor this module
provides -- pure data-shaping (packaging already-computed engine/quote
output into the envelope `RecommendationInput` defines), not a
decision or a rule, the same category of helper
`src.core.autonomous_intelligence_layer.contracts.integration.
build_intelligence_context` already is for `IntelligenceContext`.

What this module deliberately does NOT do
-------------------------------------------
1. **No orchestrator.** There is no engine here that iterates
   `DEFAULT_INTELLIGENCE_MODULE_REGISTRY` and calls `.scan()`/
   `.recommend()`/`.assess()`/etc. on whatever it finds -- that would
   be dispatch *behavior*. `CouncilEngine` remains the closest existing
   precedent for what such an orchestrator would eventually look like.
2. **No real scanning, recommendation, risk-scoring, alerting, or
   decision-fusion logic.** Every interface in `interfaces.py` is a
   calling convention only -- method name, argument shape, return
   envelope -- never an algorithm. "Do not implement fake AI. Only
   prepare scalable architecture" (verbatim instruction).
3. **No rate-limit budget decision for market-wide scanning.** SAHMK's
   free/starter daily quota (see `docs/SAHMK_INTEGRATION.md`'s "Known
   gaps") makes scanning all ~350+ Tadawul symbols a real cost/request
   question a future milestone must answer explicitly before
   `IMarketScanner` is implemented against a live provider -- this
   package does not answer it, and a future implementation must not
   silently assume an unmetered quota.
4. **No bootstrap.py, and nothing imports this package.** Every other
   registry in this codebase has a composition root that `main.py`
   imports, which is what makes it non-empty and reachable in the
   running application. This package has no such file on purpose --
   `tests/integration/test_intelligence_contracts_non_reachability.py`
   is the regression test proving `import main` does not import this
   package.
"""

from datetime import datetime
from typing import List, Optional

from src.market_data.models import MarketQuote, RecommendationInput, StockProfile


def build_recommendation_input(
    symbol: str,
    as_of: datetime,
    quote: Optional[MarketQuote] = None,
    profile: Optional[StockProfile] = None,
    technical_indicators: Optional[List] = None,
    fundamental_ratios: Optional[List] = None,
) -> RecommendationInput:
    """Packages already-computed quote/profile/indicator/ratio data
    into the envelope a future `IRecommendationEngine.recommend()`
    would receive. Does not fetch, compute, or validate anything --
    every argument is expected to already be assembled by the caller,
    exactly as `build_intelligence_context`'s caller is expected to
    have already computed the engine results it wraps.
    """
    return RecommendationInput(
        symbol=symbol,
        quote=quote,
        profile=profile,
        technical_indicators=technical_indicators if technical_indicators is not None else [],
        fundamental_ratios=fundamental_ratios if fundamental_ratios is not None else [],
        as_of=as_of,
    )
