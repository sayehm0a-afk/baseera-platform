"""Unit tests for E7's run_debate() -- exercises the real
DebateEngine/VotingSystem bookkeeping (no mocking), just with
hand-built AgentOpinionResult input.
"""

from src.ai_evolution.agents.debate import run_debate
from src.ai_evolution.agents.types import AgentOpinionResult
from src.domain.models import AgentStance


def _opinion(name, stance, confidence=70.0, reasoning="reasoning"):
    return AgentOpinionResult(agent_name=name, stance=stance, confidence=confidence, reasoning=reasoning)


class TestRunDebate:
    def test_bullish_majority_yields_buy(self):
        opinions = [
            _opinion("Technical Analyst", AgentStance.BULLISH),
            _opinion("Fundamental Analyst", AgentStance.BULLISH),
            _opinion("Risk Manager", AgentStance.BEARISH),
        ]
        outcome = run_debate("2222", opinions)
        assert outcome.final_decision == "BUY"
        assert outcome.participants == ["Technical Analyst", "Fundamental Analyst", "Risk Manager"]
        assert outcome.rounds >= 1

    def test_bearish_majority_yields_sell(self):
        opinions = [
            _opinion("Technical Analyst", AgentStance.BEARISH),
            _opinion("Fundamental Analyst", AgentStance.BEARISH),
            _opinion("Risk Manager", AgentStance.BULLISH),
        ]
        outcome = run_debate("2222", opinions)
        assert outcome.final_decision == "SELL"

    def test_tie_yields_hold(self):
        opinions = [
            _opinion("Technical Analyst", AgentStance.BULLISH),
            _opinion("Fundamental Analyst", AgentStance.BEARISH),
        ]
        outcome = run_debate("2222", opinions)
        assert outcome.final_decision == "HOLD"

    def test_no_directional_opinions_yields_hold(self):
        opinions = [
            _opinion("Macro Analyst", AgentStance.UNAVAILABLE),
            _opinion("Sentiment Analyst", AgentStance.NEUTRAL),
        ]
        outcome = run_debate("2222", opinions)
        assert outcome.final_decision == "HOLD"

    def test_agreement_level_is_a_fraction_between_0_and_1(self):
        opinions = [
            _opinion("Technical Analyst", AgentStance.BULLISH),
            _opinion("Fundamental Analyst", AgentStance.BULLISH),
        ]
        outcome = run_debate("2222", opinions)
        assert outcome.agreement_level is not None
        assert 0.0 <= outcome.agreement_level <= 1.0

    def test_each_call_uses_an_independent_session(self):
        opinions = [_opinion("Technical Analyst", AgentStance.BULLISH)]
        first = run_debate("2222", opinions)
        second = run_debate("2222", opinions)
        assert first.participants == second.participants
