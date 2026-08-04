"""Decision Engine V2 -- Phase 1 of the Basirah evolution roadmap.

Not a parallel indicator/scoring engine: this package computes zero new
indicators. It is an explainability and gating layer on top of the
existing, already-real `AIDecisionEngine` (src/analysis/decision/) --
every price, score, and signal it uses was already computed by
TechnicalAnalysisEngine/FundamentalAnalysisEngine/RecommendationEngine/
AIDecisionEngine. What this layer adds: an entry *zone* instead of a
point price, a second and third target when legitimately extendable,
a documented multi-factor sub-score breakdown, an explicit
beginner-friendly Arabic action taxonomy (STRONG_BUY_CANDIDATE ...
INSUFFICIENT_DATA), and a set of publication gates applied uniformly
whether a symbol is being scanned in bulk or analyzed one at a time
(the single-stock `/decision` and `/analyst-report` routes never ran
src.market_intelligence.publication_gate before this layer existed --
only the market-wide scanner did).
"""

from src.analysis.decision_v2.engine import DecisionEngineV2
from src.analysis.decision_v2.types import Decision, DecisionResult

__all__ = ["DecisionEngineV2", "Decision", "DecisionResult"]
