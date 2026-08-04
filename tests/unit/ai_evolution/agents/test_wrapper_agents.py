"""Unit tests for E7's non-LLM wrapper agents -- pure functions over
hand-built `DecisionFactorBreakdown` fixtures, no database, no LLM.
"""

from src.ai_evolution.agents.wrapper_agents import CategoryWrapperAgent, MacroAnalystAgent, build_wrapper_agents
from src.analysis.decision.types import DecisionFactorBreakdown
from src.domain.models import AgentStance


def _breakdown(category, points=0.0, weight=0.25, confidence=80.0, available=True, notes=None):
    return DecisionFactorBreakdown(
        category=category, points=points, weight=weight, confidence=confidence, available=available, notes=notes
    )


class TestCategoryWrapperAgent:
    def test_bullish_when_points_above_neutral_band(self):
        agent = CategoryWrapperAgent("Technical Analyst", "Technical Analysis")
        result = agent.analyze([_breakdown("Technical Analysis", points=10.0)])
        assert result.stance is AgentStance.BULLISH
        assert result.agent_name == "Technical Analyst"
        assert result.used_llm is False

    def test_bearish_when_points_below_neutral_band(self):
        agent = CategoryWrapperAgent("Technical Analyst", "Technical Analysis")
        result = agent.analyze([_breakdown("Technical Analysis", points=-10.0)])
        assert result.stance is AgentStance.BEARISH

    def test_neutral_when_points_within_neutral_band(self):
        agent = CategoryWrapperAgent("Technical Analyst", "Technical Analysis")
        result = agent.analyze([_breakdown("Technical Analysis", points=1.0)])
        assert result.stance is AgentStance.NEUTRAL

    def test_unavailable_when_category_missing(self):
        agent = CategoryWrapperAgent("Fundamental Analyst", "Fundamental Analysis")
        result = agent.analyze([_breakdown("Technical Analysis", points=10.0)])
        assert result.stance is AgentStance.UNAVAILABLE
        assert result.confidence == 0.0

    def test_unavailable_when_category_present_but_not_available(self):
        agent = CategoryWrapperAgent("Fundamental Analyst", "Fundamental Analysis")
        result = agent.analyze([_breakdown("Fundamental Analysis", points=10.0, available=False)])
        assert result.stance is AgentStance.UNAVAILABLE

    def test_reasoning_includes_notes_when_present(self):
        agent = CategoryWrapperAgent("Risk Manager", "Risk")
        result = agent.analyze([_breakdown("Risk", points=5.0, notes="Elevated volatility.")])
        assert "Elevated volatility." in result.reasoning

    def test_confidence_comes_from_breakdown(self):
        agent = CategoryWrapperAgent("Technical Analyst", "Technical Analysis")
        result = agent.analyze([_breakdown("Technical Analysis", points=10.0, confidence=65.0)])
        assert result.confidence == 65.0


class TestMacroAnalystAgent:
    def test_always_unavailable(self):
        agent = MacroAnalystAgent()
        result = agent.analyze([_breakdown("Technical Analysis", points=50.0)])
        assert result.stance is AgentStance.UNAVAILABLE
        assert result.used_llm is False
        assert "macro" in result.reasoning.lower()


class TestBuildWrapperAgents:
    def test_returns_four_agents_with_expected_names(self):
        agents = build_wrapper_agents()
        names = {agent.agent_name for agent in agents}
        assert names == {"Technical Analyst", "Fundamental Analyst", "Risk Manager", "Quant Analyst"}
