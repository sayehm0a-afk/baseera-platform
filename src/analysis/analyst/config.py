"""Environment-driven configuration for the Autonomous AI Analyst
Framework's optional real-LLM narration -- mirrors
src.news_intelligence.config's OPENAI_API_KEY / *_LLM_MODEL pattern
exactly, kept in its own small file for the same reason every other
subsystem here has one: this is deliberately not folded into
src.core.config.settings (see that module's own docstring -- Settings
is additive for Phase-10-and-later security/billing config, not a
repo-wide refactor of every subsystem's existing os.getenv pattern).
"""

import os


def get_analyst_llm_model_name() -> str:
    return os.getenv("ANALYST_LLM_MODEL", "gpt-4o-mini")


def get_analyst_llm_timeout_seconds() -> float:
    """Hard wall-clock deadline for one narration call, independent of
    OpenAILLMClient's own internal retry/backoff (which bounds retry
    *count*, not total elapsed time) -- guarantees a slow/hanging
    provider never stalls report generation beyond this ceiling."""
    return float(os.getenv("ANALYST_LLM_TIMEOUT_SECONDS", "12"))


def is_analyst_llm_narration_enabled() -> bool:
    """True iff a real OPENAI_API_KEY is configured. False is the
    correct, honest default in every environment that hasn't set one
    -- production narration then stays 100% deterministic template
    text, exactly as it always has been, never a fabricated "AI is
    connected" claim."""
    return bool(os.getenv("OPENAI_API_KEY"))
