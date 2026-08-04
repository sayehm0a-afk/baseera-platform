"""Wraps the existing `DebateEngine`/`VotingSystem` bookkeeping
(`src.core.autonomous_intelligence_layer`) into a single
`run_debate()` call -- reused exactly as built for a different
milestone, not reimplemented. Both are synchronous, in-memory,
generic argument/vote bookkeeping classes with no LLM content of
their own; this module is only the adapter mapping E7's
`AgentOpinionResult` list onto their argument/vote shapes and back.
"""

import uuid
from dataclasses import dataclass
from typing import List, Optional

from src.core.autonomous_intelligence_layer.debate_engine.debate_engine import ArgumentType, DebateEngine
from src.core.autonomous_intelligence_layer.voting_system.voting_system import VoteType, VotingSystem
from src.domain.models import AgentStance

from src.ai_evolution.agents.types import AgentOpinionResult

_DIRECTIONAL_STANCES = (AgentStance.BULLISH, AgentStance.BEARISH)


@dataclass(frozen=True)
class DebateOutcome:
    participants: List[str]
    rounds: int
    agreement_level: Optional[float]
    final_decision: Optional[str]  # "BUY" | "SELL" | "HOLD"


def _argument_type_for(stance: AgentStance) -> ArgumentType:
    if stance is AgentStance.BULLISH:
        return ArgumentType.PRO
    if stance is AgentStance.BEARISH:
        return ArgumentType.CON
    return ArgumentType.NEUTRAL


def run_debate(symbol: str, opinions: List[AgentOpinionResult]) -> DebateOutcome:
    session_key = f"{symbol}-{uuid.uuid4().hex[:8]}"
    participants = [opinion.agent_name for opinion in opinions]

    debate_engine = DebateEngine()
    debate_engine.create_session(
        session_id=session_key, topic=f"Recommendation debate for {symbol}", participants=participants
    )
    for opinion in opinions:
        debate_engine.add_argument(
            session_id=session_key,
            argument_id=f"{session_key}-{opinion.agent_name}",
            agent_id=opinion.agent_name,
            content=opinion.reasoning,
            argument_type=_argument_type_for(opinion.stance),
            confidence=max(0.0, min(1.0, opinion.confidence / 100.0)),
        )
    _, agreement_level = debate_engine.detect_consensus(session_key)

    voting_system = VotingSystem()
    voting_system.create_proposal(
        proposal_id=session_key,
        title=f"Is {symbol}'s directional evidence bullish?",
        description="Aggregates the panel's directional opinions into a single BUY/SELL/HOLD decision.",
        options=["BULLISH", "BEARISH"],
        proposer_id="AgentPanelOrchestrator",
    )
    directional_votes_cast = 0
    for opinion in opinions:
        if opinion.stance not in _DIRECTIONAL_STANCES:
            vote_type = VoteType.ABSTAIN
        else:
            vote_type = VoteType.YES if opinion.stance is AgentStance.BULLISH else VoteType.NO
            directional_votes_cast += 1
        voting_system.cast_vote(
            vote_id=f"{session_key}-vote-{opinion.agent_name}",
            voter_id=opinion.agent_name,
            proposal_id=session_key,
            vote_type=vote_type,
            confidence=max(0.0, min(1.0, opinion.confidence / 100.0)),
            reasoning=opinion.reasoning,
        )

    final_decision = "HOLD"
    if directional_votes_cast > 0:
        voting_system.close_proposal(session_key)
        proposal = voting_system.get_proposal(session_key)
        if proposal is not None and proposal.result == "APPROVED":
            final_decision = "BUY"
        elif proposal is not None and proposal.result == "REJECTED":
            final_decision = "SELL"

    return DebateOutcome(
        participants=participants,
        rounds=len(debate_engine.get_session(session_key).rounds) or 1,
        agreement_level=agreement_level,
        final_decision=final_decision,
    )
