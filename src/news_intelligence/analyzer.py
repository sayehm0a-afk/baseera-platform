"""analyzer.py: NewsAnalyzer -- entity recognition, event
classification, sentiment analysis, and impact analysis (objectives
2-5), powered by a real, already-integrated LLM client
(`src.core.llm_abstraction.OpenAILLMClient`), not a rule-based/keyword
approximation. A single headline is short enough, and the extraction
task structured enough, that this is one JSON-mode call rather than
four separate round-trips -- more token-efficient and realistic than
paying for four LLM calls to do what is fundamentally one reading
task, while `NewsAnalysisResult` still keeps each concern (entities,
category, sentiment, impact) as a clearly separated, independently
testable field.

This module applies the exact same honesty discipline this codebase
already applies to SAHMK: no fabricated "intelligence" stands in when
the real dependency is unavailable. If `OPENAI_API_KEY` is unset (or
every call fails, or a response comes back malformed), `analyze()`
returns `None` -- never a synthetic classification. The corresponding
`NewsEvent` row simply stays unanalyzed (`analyzed_at`/`analysis_model`
null) until a real key is configured or the call succeeds, mirroring
"SAHMK_API_KEY unset -> DevMarketDataProvider, disclosed, never faked"
applied to the LLM leg instead.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.analysis.ai_request_recorder import record_ai_request
from src.core.llm_abstraction.base_llm_client import BaseLLMClient
from src.core.llm_abstraction.openai_llm_client import OpenAILLMClient
from src.domain.models import AIRequestStatus, NewsCategory, NewsEntityType, SentimentLabel
from src.news_intelligence.config import get_llm_model_name
from src.news_intelligence.prompts import SYSTEM_PROMPT, build_user_prompt
from src.news_intelligence.types import EntityMention, ImpactEstimate, NewsAnalysisResult, RawNewsItem

logger = logging.getLogger(__name__)

_FEATURE = "news_intelligence:analyze"


def _clamp(value: Any, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _coerce_category(value: Any) -> NewsCategory:
    try:
        return NewsCategory(str(value).upper())
    except ValueError:
        return NewsCategory.OTHER


def _coerce_sentiment_label(value: Any) -> SentimentLabel:
    try:
        return SentimentLabel(str(value).upper())
    except ValueError:
        return SentimentLabel.NEUTRAL


def _coerce_entity_type(value: Any) -> Optional[NewsEntityType]:
    try:
        return NewsEntityType(str(value).upper())
    except ValueError:
        return None


def _parse_entities(raw_entities: Any) -> List[EntityMention]:
    entities: List[EntityMention] = []
    for raw in raw_entities or []:
        if not isinstance(raw, dict):
            continue
        entity_type = _coerce_entity_type(raw.get("entity_type"))
        if entity_type is None:
            continue
        entities.append(
            EntityMention(
                entity_type=entity_type,
                symbol=(raw.get("symbol") or None),
                sector=(raw.get("sector") or None),
                label=(raw.get("label") or None),
            )
        )
    return entities


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class NewsAnalyzer:
    """Wraps a `BaseLLMClient` (a real `OpenAILLMClient` by default).
    Never constructs a fallback "fake analyzer" -- `is_available` is
    `False`, and `analyze()` always returns `None`, when no client
    could be built (no `OPENAI_API_KEY`) or a call fails."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None, model_name: Optional[str] = None):
        if llm_client is not None:
            self._client: Optional[BaseLLMClient] = llm_client
        else:
            try:
                self._client = OpenAILLMClient(model_name=model_name or get_llm_model_name())
            except ValueError:
                self._client = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    async def analyze(
        self, item: RawNewsItem, session: Optional[Session] = None, user_id: Optional[int] = None
    ) -> Optional[NewsAnalysisResult]:
        if self._client is None:
            return None

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(item.headline, item.source)},
        ]
        model_name = getattr(self._client, "model_name", None)

        started = time.monotonic()
        try:
            response = await self._client.generate_response(messages, temperature=0.2, max_tokens=500)
        except Exception as exc:  # noqa: BLE001 -- any LLM-call failure degrades to "unanalyzed," never fabricated
            logger.warning("News analysis LLM call failed for %r: %s", item.headline[:80], exc)
            if session is not None:
                record_ai_request(
                    session, feature=_FEATURE, status=AIRequestStatus.FAILED, user_id=user_id,
                    symbol=item.symbol, model=model_name, latency_ms=(time.monotonic() - started) * 1000.0,
                    error_message=str(exc)[:500],
                )
            return None
        latency_ms = (time.monotonic() - started) * 1000.0

        parsed = _extract_json(response.get("content", ""))
        usage = response.get("usage") or {}
        if session is not None:
            record_ai_request(
                session, feature=_FEATURE,
                status=AIRequestStatus.SUCCESS if parsed is not None else AIRequestStatus.FAILED,
                user_id=user_id, symbol=item.symbol, model=response.get("model") or model_name,
                prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"), latency_ms=latency_ms,
                error_message=None if parsed is not None else "LLM response was not valid JSON",
            )
        if parsed is None:
            logger.warning("News analysis LLM response was not valid JSON for %r", item.headline[:80])
            return None

        impact = ImpactEstimate(
            short_term=_clamp(parsed.get("short_term_impact"), -1.0, 1.0),
            medium_term=_clamp(parsed.get("medium_term_impact"), -1.0, 1.0),
            long_term=_clamp(parsed.get("long_term_impact"), -1.0, 1.0),
            price_impact=_clamp(parsed.get("price_impact"), 0.0, 1.0),
            risk_impact=_clamp(parsed.get("risk_impact"), 0.0, 1.0),
            volatility_impact=_clamp(parsed.get("volatility_impact"), 0.0, 1.0),
        )
        return NewsAnalysisResult(
            entities=_parse_entities(parsed.get("entities")),
            category=_coerce_category(parsed.get("category")),
            sentiment_score=_clamp(parsed.get("sentiment_score"), -1.0, 1.0),
            sentiment_label=_coerce_sentiment_label(parsed.get("sentiment_label")),
            confidence=_clamp(parsed.get("confidence"), 0.0, 100.0),
            explanation=str(parsed.get("explanation") or ""),
            impact=impact,
            model=response.get("model") or model_name,
        )
