"""get_analyst_engine(): the one place production code decides whether
the Autonomous AI Analyst Framework narrates with a real LLM or stays
fully deterministic -- mirrors src.market_data.provider_factory's
"decide once, here, not scattered across call sites" shape.

Never constructs OpenAILLMAdapter unless is_analyst_llm_narration_enabled()
is true (a real OPENAI_API_KEY is configured); every environment that
hasn't set one gets exactly today's behavior, unchanged.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.analysis.analyst.analyst_engine import AnalystEngine
from src.analysis.analyst.config import is_analyst_llm_narration_enabled
from src.analysis.analyst.llm_adapter import LLMAdapter
from src.analysis.analyst.reasoning_pipeline import ReasoningPipeline

logger = logging.getLogger(__name__)


def get_llm_adapter() -> Optional[LLMAdapter]:
    if not is_analyst_llm_narration_enabled():
        return None
    from src.analysis.analyst.openai_llm_adapter import OpenAILLMAdapter

    try:
        return OpenAILLMAdapter()
    except ValueError:
        # OPENAI_API_KEY was present a moment ago (the check above) but
        # OpenAILLMClient's own constructor no longer sees it -- an
        # unlikely race, not worth failing the request over. Falls
        # back to deterministic-only narration, the same safe default
        # as never having configured a key at all.
        logger.warning("Analyst LLM narration was enabled but OpenAILLMAdapter construction failed.")
        return None


def get_analyst_engine(session: Session) -> AnalystEngine:
    return AnalystEngine(pipeline=ReasoningPipeline(llm_adapter=get_llm_adapter(), session=session))
