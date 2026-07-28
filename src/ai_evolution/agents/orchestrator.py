"""AgentPanelOrchestrator: runs the full E7 panel for one live
recommendation and persists the result. Never raises -- every step is
wrapped so a panel failure degrades to "no panel data for this
recommendation" rather than breaking the live scan that called it
(`MarketScanner._scan_one_with_retry` retries on any unhandled
exception; a bug in this orchestration must never trigger a wasted
rescan of a symbol whose real `AnalystEngine` decision already
succeeded).

Runs once per symbol/day, alongside the existing live scan (called
from `MarketIntelligenceRepository.save_symbol_records`, after a
`RecommendationSnapshot` is written) -- gated behind
`AGENT_PANEL_ENABLED` (default off) independent of whether real LLM
calls are additionally enabled (`OPENAI_API_KEY`).
"""

import logging
from typing import List

from sqlalchemy.orm import Session

from src.ai_evolution.agents.conflict import should_trigger_debate
from src.ai_evolution.agents.debate import run_debate
from src.ai_evolution.agents.llm_agents import JudgeAgent, NewsAnalystAgent, SentimentAnalystAgent
from src.ai_evolution.agents.llm_factory import get_agent_panel_llm_adapter
from src.ai_evolution.agents.types import AgentOpinionResult
from src.ai_evolution.agents.wrapper_agents import MacroAnalystAgent, build_wrapper_agents
from src.analysis.decision.types import InvestmentDecision
from src.domain.models import AgentOpinion, AgentStance, DebateSession, RecommendationSnapshot

logger = logging.getLogger(__name__)


def _persist_opinions(session: Session, snapshot_id: int, opinions: List[AgentOpinionResult]) -> None:
    for opinion in opinions:
        session.add(
            AgentOpinion(
                snapshot_id=snapshot_id,
                agent_name=opinion.agent_name,
                stance=opinion.stance,
                confidence=opinion.confidence,
                reasoning=opinion.reasoning,
                used_llm=opinion.used_llm,
            )
        )


class AgentPanelOrchestrator:
    async def run_panel(
        self, session: Session, snapshot: RecommendationSnapshot, decision: InvestmentDecision, symbol: str
    ) -> None:
        try:
            await self._run_panel(session, snapshot, decision, symbol)
        except Exception:  # noqa: BLE001 -- deliberate: this coroutine must never raise, see module docstring.
            logger.exception("Agent panel failed for %s -- continuing without panel data.", symbol)

    async def _run_panel(
        self, session: Session, snapshot: RecommendationSnapshot, decision: InvestmentDecision, symbol: str
    ) -> None:
        opinions: List[AgentOpinionResult] = [
            agent.analyze(decision.breakdown) for agent in build_wrapper_agents()
        ]
        opinions.append(MacroAnalystAgent().analyze(decision.breakdown))

        llm_adapter = get_agent_panel_llm_adapter()
        news_opinion = await NewsAnalystAgent(llm_adapter).analyze(session, symbol)
        sentiment_opinion = await SentimentAnalystAgent(llm_adapter).analyze(session, symbol)
        opinions.append(news_opinion)
        opinions.append(sentiment_opinion)

        _persist_opinions(session, snapshot.id, opinions)

        if news_opinion.stance is not AgentStance.UNAVAILABLE and news_opinion.used_llm:
            snapshot.news_summary = news_opinion.reasoning[:2000]

        if should_trigger_debate(decision.breakdown):
            outcome = run_debate(symbol, opinions)
            judge = JudgeAgent(llm_adapter)
            judge_explanation = await judge.synthesize(
                symbol, opinions, outcome.final_decision, outcome.agreement_level
            )

            session.add(
                DebateSession(
                    snapshot_id=snapshot.id,
                    participants=outcome.participants,
                    rounds=outcome.rounds,
                    agreement_level=outcome.agreement_level,
                    final_decision=outcome.final_decision,
                    judge_explanation=judge_explanation or None,
                )
            )
            snapshot.agent_debate_summary = {
                "final_decision": outcome.final_decision,
                "agreement_level": outcome.agreement_level,
                "participants": outcome.participants,
                "judge_explanation": judge_explanation,
            }

        session.commit()
