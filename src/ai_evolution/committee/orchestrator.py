"""InvestmentCommitteeOrchestrator: runs all eight committee agents
for one live Decision Engine V2 decision, builds the consensus, and
persists both -- the single entry point `/decision-v2` calls. Never
raises (same discipline as `AgentPanelOrchestrator.run_panel`, see its
own docstring): a committee failure must never break the underlying
decision response it augments.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from src.ai_evolution.committee import agents as committee_agents
from src.ai_evolution.committee.consensus import build_consensus
from src.ai_evolution.committee.types import AgentVerdict, ConsensusResult, verdict_to_dict
from src.analysis.decision.types import InvestmentDecision
from src.analysis.decision_v2.types import DecisionResult
from src.domain.models import CommitteeAgentOpinion, CommitteeConsensus

logger = logging.getLogger(__name__)


class InvestmentCommitteeOrchestrator:
    async def run_committee(
        self,
        session: Session,
        decision_v2_snapshot_id: int,
        symbol: str,
        investment_decision: InvestmentDecision,
        result: DecisionResult,
        news_events: Optional[List[dict]] = None,
    ) -> Optional[ConsensusResult]:
        try:
            return await self._run_committee(
                session, decision_v2_snapshot_id, symbol, investment_decision, result, news_events or [],
            )
        except Exception:  # noqa: BLE001 -- deliberate: this coroutine must never raise, see module docstring.
            logger.exception("Investment committee failed for %s -- continuing without committee data.", symbol)
            return None

    async def _run_committee(
        self,
        session: Session,
        decision_v2_snapshot_id: int,
        symbol: str,
        investment_decision: InvestmentDecision,
        result: DecisionResult,
        news_events: List[dict],
    ) -> ConsensusResult:
        opinions: List[AgentVerdict] = [
            committee_agents.analyze_technical(investment_decision, result),
            committee_agents.analyze_fundamental(investment_decision, result),
            await committee_agents.analyze_news(session, symbol, news_events),
            committee_agents.analyze_market_sentiment(result),
            committee_agents.analyze_risk(investment_decision, result),
            committee_agents.analyze_liquidity_volume(result),
            committee_agents.analyze_macro(),
            committee_agents.analyze_portfolio_allocation(investment_decision, result),
        ]

        consensus = build_consensus(symbol, opinions)

        for verdict in opinions:
            session.add(
                CommitteeAgentOpinion(
                    decision_v2_snapshot_id=decision_v2_snapshot_id,
                    agent_name=verdict.agent_name,
                    agent_role=verdict.role,
                    stance=verdict.stance,
                    confidence=verdict.confidence,
                    reasoning=verdict.reasoning,
                    evidence=list(verdict.evidence),
                    rejection_reasons=list(verdict.rejection_reasons),
                    used_llm=verdict.used_llm,
                )
            )

        session.add(
            CommitteeConsensus(
                decision_v2_snapshot_id=decision_v2_snapshot_id,
                final_decision=consensus.final_decision,
                final_confidence=consensus.final_confidence,
                participant_count=consensus.participant_count,
                directional_count=consensus.directional_count,
                agreement_pct=consensus.agreement_pct,
                disagreement_pct=consensus.disagreement_pct,
                disagreement_score=consensus.disagreement_score,
                most_optimistic_agent=consensus.most_optimistic_agent,
                most_optimistic_stance=consensus.most_optimistic_stance,
                most_conservative_agent=consensus.most_conservative_agent,
                most_conservative_stance=consensus.most_conservative_stance,
                consensus_reasoning_ar=consensus.consensus_reasoning_ar,
                rejected_alternatives=[
                    {
                        "agent_name": r.agent_name, "role": r.role, "stance": r.stance.value,
                        "confidence": r.confidence, "reasoning": r.reasoning,
                        "rejection_reason": r.rejection_reason,
                    }
                    for r in consensus.rejected_alternatives
                ],
                weighted_votes=consensus.weighted_votes,
            )
        )
        session.commit()
        return consensus


__all__ = ["InvestmentCommitteeOrchestrator", "verdict_to_dict"]
