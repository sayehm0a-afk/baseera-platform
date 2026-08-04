"""compute_investment_decision: the single call site, across the whole
codebase, that turns an `AnalysisContext` into an `InvestmentDecision`
by invoking `AIDecisionEngine.decide()`.

Introduced during the Phase 2 Foundation Cleanup. Before this module
existed, `AIDecisionEngine().decide(context)` was called from three
independent places -- `GET /stocks/{symbol}/decision`,
`GET /stocks/{symbol}/decision-v2`, and `AnalystEngine.analyze()`
(itself used by `GET /stocks/{symbol}/analyst-report`, the market
scanner, and portfolio intelligence) -- each wiring the same engine
together on its own. Nothing about `AIDecisionEngine`'s behavior,
signature, or output changes here; this module only removes the
duplicated call site so a future change to *how* an `InvestmentDecision`
gets computed has exactly one place to happen.

Deliberately takes an already-built `AnalysisContext`, not a bare
symbol -- assembling that context (and deciding what "not enough data"
means for the caller: an HTTP 422 for a REST route, a silently-skipped
symbol for a market scan) stays the caller's concern, exactly per
`context_builder.py`'s own layering rule, which this module follows.
"""

from typing import Optional

from src.analysis.decision.ai_decision_engine import AIDecisionEngine
from src.analysis.decision.types import InvestmentDecision
from src.analysis.recommendation.types import AnalysisContext


def compute_investment_decision(
    context: AnalysisContext,
    *,
    decision_engine: Optional[AIDecisionEngine] = None,
    requesting_user_id: Optional[int] = None,
) -> InvestmentDecision:
    """Pass `decision_engine` to reuse a pre-configured `AIDecisionEngine`
    (e.g. custom contributors/tuning, as `AnalystEngine` already
    supports) instead of the default one. `requesting_user_id` is
    forwarded unchanged to `AIDecisionEngine.decide()` for AI-usage
    instrumentation -- omit it (as `/decision` and `/decision-v2`
    always have) when the call should not be attributed to a user's AI
    usage; pass it (as `/analyst-report` always has) when it should.
    """
    engine = decision_engine or AIDecisionEngine()
    return engine.decide(context, requesting_user_id=requesting_user_id)
