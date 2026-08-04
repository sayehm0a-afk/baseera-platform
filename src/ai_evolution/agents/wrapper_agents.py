"""Non-LLM panel members: Technical/Fundamental/Risk/Quant analysts
are thin, structured wrappers over `InvestmentDecision.breakdown`
(already-deterministic engine output) -- no new computation, no LLM
call, and therefore zero risk of introducing a number the platform
didn't already compute. Macro Analyst is a disclosed no-op: no real
macro data source exists in this codebase yet (the same honest gap
`external_factor_contributors.py`'s macro contributor already
discloses), so it always reports UNAVAILABLE rather than fabricating
an opinion.

These are deliberately plain classes, not `src.core.base_agent
.BaseAgent` subclasses -- that base class is a heavyweight,
tool-calling/lifecycle abstraction (activate/pause/terminate, a tool
registry, an LLM client slot) built for a different kind of agent
entirely; forcing these simple, stateless, single-method wrappers to
inherit it would add ceremony with no real behavior. A deliberate,
disclosed deviation from the literal "every agent inherits BaseAgent"
request, in the same spirit as this design's other stated departures
(the 16-to-9 agent collapse, excluding temperature scaling in E3).
"""

from typing import List, Optional

from src.ai_evolution.agents.types import AgentOpinionResult
from src.analysis.decision.types import DecisionFactorBreakdown
from src.domain.models import AgentStance

# A category's `points` are signed and centered on 0 (see
# DecisionFactorBreakdown's own docstring) -- this is the threshold
# below which a category's tilt is reported as NEUTRAL rather than a
# direction, matching the small-noise-band convention already used
# elsewhere in this codebase (e.g. RSI/MACD neutral zones).
_NEUTRAL_BAND = 3.0


def _stance_from_points(points: float) -> AgentStance:
    if points >= _NEUTRAL_BAND:
        return AgentStance.BULLISH
    if points <= -_NEUTRAL_BAND:
        return AgentStance.BEARISH
    return AgentStance.NEUTRAL


def _find_breakdown(breakdown: List[DecisionFactorBreakdown], category: str) -> Optional[DecisionFactorBreakdown]:
    for item in breakdown:
        if item.category == category:
            return item
    return None


class CategoryWrapperAgent:
    """Wraps one `DecisionFactorBreakdown` category as a structured
    opinion. `agent_name`/`category`/`display_label` are supplied at
    construction so one class serves the Technical, Fundamental, Risk,
    and Quant (mapped to the Momentum category -- the closest existing
    quantitative/statistical signal; no separate "quant" contributor
    exists in `AIDecisionEngine.default_contributors()`, a disclosed
    mapping choice) analysts without four near-duplicate classes."""

    def __init__(self, agent_name: str, category: str):
        self.agent_name = agent_name
        self._category = category

    def analyze(self, breakdown: List[DecisionFactorBreakdown]) -> AgentOpinionResult:
        item = _find_breakdown(breakdown, self._category)
        if item is None or not item.available:
            return AgentOpinionResult(
                agent_name=self.agent_name,
                stance=AgentStance.UNAVAILABLE,
                confidence=0.0,
                reasoning=f"No {self._category} data was available for this recommendation.",
                used_llm=False,
            )

        stance = _stance_from_points(item.points)
        reasoning = f"{self._category} contributed {item.points:+.1f} points (weight {item.weight:.2f})."
        if item.notes:
            reasoning += f" {item.notes}"

        return AgentOpinionResult(
            agent_name=self.agent_name,
            stance=stance,
            confidence=item.confidence,
            reasoning=reasoning,
            used_llm=False,
        )


class MacroAnalystAgent:
    """Always UNAVAILABLE -- no real macro data source (rates,
    inflation, GDP, oil price for Tadawul's energy-heavy weighting,
    etc.) exists anywhere in this codebase yet. Disclosed honestly
    rather than fabricating a plausible-sounding macro opinion."""

    agent_name = "Macro Analyst"

    def analyze(self, breakdown: List[DecisionFactorBreakdown]) -> AgentOpinionResult:
        return AgentOpinionResult(
            agent_name=self.agent_name,
            stance=AgentStance.UNAVAILABLE,
            confidence=0.0,
            reasoning="No real macroeconomic data source is integrated in this codebase yet.",
            used_llm=False,
        )


def build_wrapper_agents() -> List[CategoryWrapperAgent]:
    return [
        CategoryWrapperAgent("Technical Analyst", "Technical Analysis"),
        CategoryWrapperAgent("Fundamental Analyst", "Fundamental Analysis"),
        CategoryWrapperAgent("Risk Manager", "Risk"),
        CategoryWrapperAgent("Quant Analyst", "Momentum"),
    ]
