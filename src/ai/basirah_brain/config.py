"""Basirah Brain's own model-provider configuration -- deliberately
separate from `src.analysis.analyst.config` (the narration-only LLM
config), since Stage 1's provider selection is an independent product
decision, not tied to the analyst-report rephrasing feature.

Low temperature / no creative sampling by design (financial analysis
needs reproducibility, not creative variance) -- see module docstring
of `providers/openai_provider.py` for how `seed` is used when the
underlying model supports it.
"""

import os


def get_basirah_brain_model_name() -> str:
    return os.getenv("BASIRAH_BRAIN_MODEL_NAME", "gpt-4o-mini")


def get_basirah_brain_timeout_seconds() -> float:
    return float(os.getenv("BASIRAH_BRAIN_TIMEOUT_SECONDS", "30"))


def get_basirah_brain_temperature() -> float:
    return float(os.getenv("BASIRAH_BRAIN_TEMPERATURE", "0.1"))


def get_basirah_brain_seed() -> int:
    return int(os.getenv("BASIRAH_BRAIN_SEED", "7"))


def get_basirah_brain_max_output_tokens() -> int:
    return int(os.getenv("BASIRAH_BRAIN_MAX_OUTPUT_TOKENS", "1500"))


def get_basirah_brain_max_provider_call_attempts() -> int:
    """Pre-merge hardening audit (Finding F4): the shared, existing
    `OpenAILLMClient` this provider reuses internally retries up to its
    OWN `max_retries` config (default 3, defined by `BaseLLMClient`/
    `OpenAILLMClient` -- see src/core/llm_abstraction/) on any exception,
    including a genuinely permanent failure. That is correct, intended
    behavior for its other production callers (NewsAnalyzer,
    OpenAILLMAdapter) and this remediation does NOT change that shared,
    global policy.

    Basirah Brain instead passes its OWN, explicit, LOCAL `config` when
    it constructs its own `OpenAILLMClient` instance (see
    providers/openai_provider.py), so its worst-case provider-call count
    per `analyze()` is a small, independently-configured, always-provable
    number -- not silently inherited from a shared default that could
    change for unrelated reasons elsewhere in the codebase. Default 1:
    a single attempt, no internal retry, relying on the provider's own
    outer `asyncio.wait_for` timeout for latency bounding instead."""
    return int(os.getenv("BASIRAH_BRAIN_MAX_PROVIDER_CALL_ATTEMPTS", "1"))
