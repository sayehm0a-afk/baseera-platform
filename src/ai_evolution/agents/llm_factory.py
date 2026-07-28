"""get_agent_panel_llm_adapter(): the one place production code decides
whether the E7 agent panel's News/Sentiment/Judge agents use a real
LLM -- mirrors `src.analysis.analyst.analyst_engine_factory
.get_llm_adapter()` exactly (same lazy-import + `try/except ValueError`
+ `None`-fallback shape), reusing `OpenAILLMAdapter` itself rather than
a second, unaudited adapter class.
"""

import logging
from typing import Optional

from src.ai_evolution.config import is_agent_panel_llm_enabled
from src.analysis.analyst.llm_adapter import LLMAdapter

logger = logging.getLogger(__name__)


def get_agent_panel_llm_adapter() -> Optional[LLMAdapter]:
    if not is_agent_panel_llm_enabled():
        return None
    from src.analysis.analyst.openai_llm_adapter import OpenAILLMAdapter

    try:
        return OpenAILLMAdapter()
    except ValueError:
        logger.warning("Agent panel LLM narration was enabled but OpenAILLMAdapter construction failed.")
        return None
