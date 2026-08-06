"""Unit tests for the Consensus Engine -- pure arithmetic over
hand-built `AgentVerdict` lists, no database, no LLM.
"""

from src.ai_evolution.committee.consensus import build_consensus
from src.ai_evolution.committee.types import AgentVerdict
from src.domain.models import AgentStance


def _verdict(agent_name, role, stance, confidence=70.0, reasoning="r", evidence=None, rejection_reasons=None):
    return AgentVerdict(
        agent_name=agent_name, role=role, stance=stance, confidence=confidence, reasoning=reasoning,
        evidence=evidence or [], rejection_reasons=rejection_reasons or [],
    )


class TestBuildConsensus:
    def test_no_opinions_yields_hold_with_zero_confidence(self):
        consensus = build_consensus("2222", [])
        assert consensus.final_decision == "HOLD"
        assert consensus.final_confidence == 0.0
        assert consensus.agreement_pct == 0.0
        assert consensus.most_optimistic_agent is None
        assert consensus.most_conservative_agent is None

    def test_all_unavailable_yields_hold(self):
        opinions = [_verdict("A", "technical", AgentStance.UNAVAILABLE, confidence=0.0)]
        consensus = build_consensus("2222", opinions)
        assert consensus.final_decision == "HOLD"
        assert consensus.participant_count == 1
        assert consensus.directional_count == 0

    def test_unanimous_bullish_yields_buy_full_agreement(self):
        opinions = [
            _verdict("Technical", "technical", AgentStance.BULLISH, confidence=80.0),
            _verdict("Fundamental", "fundamental", AgentStance.BULLISH, confidence=70.0),
            _verdict("Risk", "risk", AgentStance.BULLISH, confidence=60.0),
        ]
        consensus = build_consensus("2222", opinions)
        assert consensus.final_decision == "BUY"
        assert consensus.agreement_pct == 100.0
        assert consensus.disagreement_pct == 0.0
        assert consensus.rejected_alternatives == []
        assert consensus.final_confidence > 0

    def test_unanimous_bearish_yields_sell(self):
        opinions = [
            _verdict("Technical", "technical", AgentStance.BEARISH, confidence=80.0),
            _verdict("Risk", "risk", AgentStance.BEARISH, confidence=60.0),
        ]
        consensus = build_consensus("2222", opinions)
        assert consensus.final_decision == "SELL"
        assert consensus.agreement_pct == 100.0

    def test_dissenting_agent_appears_in_rejected_alternatives(self):
        opinions = [
            _verdict("Technical", "technical", AgentStance.BULLISH, confidence=90.0),
            _verdict("Fundamental", "fundamental", AgentStance.BULLISH, confidence=85.0),
            _verdict("Risk", "risk", AgentStance.BEARISH, confidence=40.0, reasoning="مخاطر مرتفعة"),
        ]
        consensus = build_consensus("2222", opinions)
        assert consensus.final_decision == "BUY"  # higher-weighted bullish side wins (risk role weight 1.3 vs low confidence)
        names = [r.agent_name for r in consensus.rejected_alternatives]
        assert "Risk" in names
        assert "مخاطر مرتفعة" in [r.reasoning for r in consensus.rejected_alternatives][0]
        assert consensus.disagreement_pct > 0

    def test_most_optimistic_and_conservative_agents_identified(self):
        opinions = [
            _verdict("Technical", "technical", AgentStance.BULLISH, confidence=95.0),
            _verdict("Risk", "risk", AgentStance.BEARISH, confidence=90.0),
            _verdict("Macro", "macro", AgentStance.NEUTRAL, confidence=10.0),
        ]
        consensus = build_consensus("2222", opinions)
        assert consensus.most_optimistic_agent == "Technical"
        assert consensus.most_conservative_agent == "Risk"

    def test_unavailable_agents_excluded_from_agreement_math(self):
        opinions = [
            _verdict("Technical", "technical", AgentStance.BULLISH, confidence=80.0),
            _verdict("Fundamental", "fundamental", AgentStance.BULLISH, confidence=75.0),
            _verdict("Macro", "macro", AgentStance.UNAVAILABLE, confidence=0.0),
        ]
        consensus = build_consensus("2222", opinions)
        assert consensus.participant_count == 3
        assert consensus.agreement_pct == 100.0  # only the two opinionated agents count

    def test_weighted_votes_dict_has_an_entry_per_opinion(self):
        opinions = [
            _verdict("Technical", "technical", AgentStance.BULLISH, confidence=80.0),
            _verdict("Macro", "macro", AgentStance.UNAVAILABLE, confidence=0.0),
        ]
        consensus = build_consensus("2222", opinions)
        assert set(consensus.weighted_votes.keys()) == {"Technical", "Macro"}
        assert consensus.weighted_votes["Macro"] == 0.0
        assert consensus.weighted_votes["Technical"] > 0.0

    def test_consensus_reasoning_mentions_symbol_and_decision(self):
        opinions = [_verdict("Technical", "technical", AgentStance.BULLISH, confidence=80.0)]
        consensus = build_consensus("2222", opinions)
        assert "2222" in consensus.consensus_reasoning_ar
        assert "شراء" in consensus.consensus_reasoning_ar

    def test_disagreement_score_higher_for_more_conflicted_opinions(self):
        agreeing = [
            _verdict("A", "technical", AgentStance.BULLISH, confidence=80.0),
            _verdict("B", "fundamental", AgentStance.BULLISH, confidence=80.0),
        ]
        conflicted = [
            _verdict("A", "technical", AgentStance.BULLISH, confidence=90.0),
            _verdict("B", "fundamental", AgentStance.BEARISH, confidence=90.0),
        ]
        low = build_consensus("2222", agreeing).disagreement_score
        high = build_consensus("2222", conflicted).disagreement_score
        assert high > low
