"""The panel's real-LLM-calling members: News Analyst, Sentiment
Analyst, and the Judge. All three reuse
`src.analysis.analyst.openai_llm_adapter.OpenAILLMAdapter` verbatim --
the exact same hard-timeout / never-raises / numeric-grounding-
rejection safety pattern R3 already proved in production for the
Autonomous AI Analyst Framework's narration, not a new, unaudited
adapter. Every prompt built here explicitly includes every number the
model is allowed to cite (sentiment scores, confidence percentages,
article counts already computed by `NewsIntelligenceService`, or
already-computed agent confidences) so a legitimate number can pass
the grounding check while an invented one cannot.

News/Sentiment agents never run when `OPENAI_API_KEY` is unset (see
`src.ai_evolution.config.is_agent_panel_llm_enabled`) -- they report
UNAVAILABLE instead, the same honest-omission discipline the rest of
the panel already uses for Macro Analyst.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from src.ai_evolution.agents.types import AgentOpinionResult
from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationRequest
from src.domain.models import AgentStance
from src.news_intelligence.service import NewsIntelligenceService
from src.news_intelligence.types import SymbolNewsSentiment

logger = logging.getLogger(__name__)

_SENTIMENT_LOOKBACK_DAYS = 7
_STANCE_POSITIVE_THRESHOLD = 0.15
_STANCE_NEGATIVE_THRESHOLD = -0.15


def _stance_from_sentiment_score(score: float) -> AgentStance:
    if score >= _STANCE_POSITIVE_THRESHOLD:
        return AgentStance.BULLISH
    if score <= _STANCE_NEGATIVE_THRESHOLD:
        return AgentStance.BEARISH
    return AgentStance.NEUTRAL


def _load_symbol_sentiment(session: Session, symbol: str) -> Optional[SymbolNewsSentiment]:
    service = NewsIntelligenceService()
    return service.get_symbol_sentiment(session, symbol, lookback_days=_SENTIMENT_LOOKBACK_DAYS)


def _grounding_facts(sentiment: SymbolNewsSentiment) -> str:
    lines = [
        f"Aggregate sentiment score: {sentiment.sentiment_score:.2f} (range -1.0 to 1.0).",
        f"Article count: {sentiment.article_count}.",
    ]
    for event in sentiment.events[:5]:
        lines.append(
            f"- \"{event.headline}\" (category={event.category.value}, "
            f"sentiment={event.sentiment_score:.2f}, confidence={event.confidence:.0f}, "
            f"impact_points={event.impact_points:+.1f})"
        )
    return "\n".join(lines)


async def _grounded_completion(adapter: LLMAdapter, symbol: str, facts: str, instruction: str) -> str:
    prompt = (
        f"Symbol: {symbol}\n"
        f"Facts (do not invent any number not listed here):\n{facts}\n\n"
        f"{instruction}"
    )
    result = await adapter.generate(LLMGenerationRequest(prompt=prompt, max_tokens=150, temperature=0.2))
    return result.text


class NewsAnalystAgent:
    agent_name = "News Analyst"

    def __init__(self, llm_adapter: Optional[LLMAdapter]):
        self._llm_adapter = llm_adapter

    async def analyze(self, session: Session, symbol: str) -> AgentOpinionResult:
        if self._llm_adapter is None:
            return AgentOpinionResult(
                agent_name=self.agent_name, stance=AgentStance.UNAVAILABLE, confidence=0.0,
                reasoning="Real-LLM agent narration is disabled (no OPENAI_API_KEY configured).", used_llm=False,
            )

        sentiment = _load_symbol_sentiment(session, symbol)
        if sentiment is None or sentiment.article_count == 0:
            return AgentOpinionResult(
                agent_name=self.agent_name, stance=AgentStance.UNAVAILABLE, confidence=0.0,
                reasoning=f"No analyzed news found for {symbol} in the last {_SENTIMENT_LOOKBACK_DAYS} days.",
                used_llm=False,
            )

        facts = _grounding_facts(sentiment)
        summary = await _grounded_completion(
            self._llm_adapter, symbol, facts,
            "Summarize what this news means for the stock in one or two sentences, "
            "using only the facts above.",
        )
        stance = _stance_from_sentiment_score(sentiment.sentiment_score)
        reasoning = summary if summary else (
            f"{sentiment.article_count} recent article(s), aggregate sentiment {sentiment.sentiment_score:.2f}."
        )
        return AgentOpinionResult(
            agent_name=self.agent_name, stance=stance, confidence=min(100.0, sentiment.article_count * 20.0),
            reasoning=reasoning, used_llm=bool(summary),
        )


class SentimentAnalystAgent:
    agent_name = "Sentiment Analyst"

    def __init__(self, llm_adapter: Optional[LLMAdapter]):
        self._llm_adapter = llm_adapter

    async def analyze(self, session: Session, symbol: str) -> AgentOpinionResult:
        if self._llm_adapter is None:
            return AgentOpinionResult(
                agent_name=self.agent_name, stance=AgentStance.UNAVAILABLE, confidence=0.0,
                reasoning="Real-LLM agent narration is disabled (no OPENAI_API_KEY configured).", used_llm=False,
            )

        sentiment = _load_symbol_sentiment(session, symbol)
        if sentiment is None or sentiment.article_count == 0:
            return AgentOpinionResult(
                agent_name=self.agent_name, stance=AgentStance.UNAVAILABLE, confidence=0.0,
                reasoning=f"No analyzed news found for {symbol} in the last {_SENTIMENT_LOOKBACK_DAYS} days.",
                used_llm=False,
            )

        facts = _grounding_facts(sentiment)
        rationale = await _grounded_completion(
            self._llm_adapter, symbol, facts,
            "In one sentence, explain whether market sentiment toward this stock is "
            "positive, negative, or mixed, using only the facts above.",
        )
        stance = _stance_from_sentiment_score(sentiment.sentiment_score)
        reasoning = rationale if rationale else f"Aggregate sentiment score {sentiment.sentiment_score:.2f}."
        return AgentOpinionResult(
            agent_name=self.agent_name, stance=stance, confidence=abs(sentiment.sentiment_score) * 100.0,
            reasoning=reasoning, used_llm=bool(rationale),
        )


class JudgeAgent:
    """The one LLM call in a debate: synthesizes the panel's opinions
    and the vote outcome into a short, grounded explanation. Never
    introduces a new number, price, or recommendation -- it only
    explains a decision the deterministic voting/debate bookkeeping
    already made."""

    agent_name = "Judge"

    def __init__(self, llm_adapter: Optional[LLMAdapter]):
        self._llm_adapter = llm_adapter

    async def synthesize(
        self, symbol: str, opinions: List[AgentOpinionResult], final_decision: Optional[str], agreement_level: Optional[float]
    ) -> str:
        if self._llm_adapter is None:
            return ""

        lines = [f"Final decision: {final_decision or 'no majority'}."]
        if agreement_level is not None:
            lines.append(f"Agreement level: {agreement_level:.2f} (0.0 to 1.0).")
        for opinion in opinions:
            lines.append(f"- {opinion.agent_name}: {opinion.stance.value} (confidence {opinion.confidence:.0f}).")
        facts = "\n".join(lines)

        explanation = await _grounded_completion(
            self._llm_adapter, symbol, facts,
            "In two or three sentences, explain why the panel reached this decision despite the "
            "disagreement, using only the facts above.",
        )
        return explanation
