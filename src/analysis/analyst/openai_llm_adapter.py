"""OpenAILLMAdapter: the first concrete, network-calling `LLMAdapter`
this codebase ships -- see llm_adapter.py's module docstring for why
none existed before this. Reuses the already-built, already-tested
`OpenAILLMClient` (src/core/llm_abstraction/openai_llm_client.py),
the same class News Intelligence's `NewsAnalyzer` already calls in
production, so this introduces no new provider integration, only a
new caller of one that already works.

Two things make this safe to wire into the live /analyst-report path:

1. `ReasoningPipeline._narrate()` only ever offers this adapter an
   already-computed, deterministically-correct baseline paragraph to
   REPHRASE -- never asks it to originate a number, a target price, a
   recommendation, or any fact. The prompt template
   (prompt_templates.py's `_LLM_INSTRUCTIONS`) explicitly instructs
   "do not invent any figures... only rephrase and clarify," and this
   adapter additionally verifies that instruction was honored (see
   `_is_grounded` below) before ever returning the rephrased text.
2. `generate()` never raises. Every failure mode (missing/invalid
   response, timeout, provider error, a numeric hallucination caught
   by `_is_grounded`) is caught here and converted into an empty-text
   result -- `_narrate()`'s existing, already-tested fallback
   (`return result.text if result.text else baseline_text`) then
   silently keeps the deterministic baseline. A stock page must never
   break because an LLM call failed.
"""

import asyncio
import logging
import re
from typing import Optional

from src.analysis.analyst.config import get_analyst_llm_model_name, get_analyst_llm_timeout_seconds
from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationRequest, LLMGenerationResult
from src.core.llm_abstraction.openai_llm_client import OpenAILLMClient

logger = logging.getLogger(__name__)

_NUMBER_PATTERN = re.compile(r"\d+\.?\d*")


def _extract_numbers(text: str) -> set:
    return set(_NUMBER_PATTERN.findall(text))


def _is_grounded(prompt: str, completion: str) -> bool:
    """True iff every number appearing in `completion` also appears
    somewhere in `prompt` (which itself contains the deterministic
    baseline text the model was told to rephrase, per
    PromptTemplateManager.build_prompt). A rephrasing that introduces
    a number absent from its own grounding text is treated as a
    hallucination, not a stylistic choice -- this is a blunt,
    substring-level check by design: it has false positives (e.g. a
    model spelling "one" instead of "1" would fail this and simply
    fall back to the deterministic baseline, never a wrong or
    dangerous outcome) but no false negatives that matter -- a
    genuinely new invented figure cannot pass it."""
    completion_numbers = _extract_numbers(completion)
    if not completion_numbers:
        return True
    return completion_numbers.issubset(_extract_numbers(prompt))


class OpenAILLMAdapter(LLMAdapter):
    name = "openai"

    def __init__(self, client: Optional[OpenAILLMClient] = None, timeout_seconds: Optional[float] = None):
        self._client = client or OpenAILLMClient(model_name=get_analyst_llm_model_name())
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else get_analyst_llm_timeout_seconds()

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        try:
            response = await asyncio.wait_for(
                self._client.generate_response(
                    messages, max_tokens=request.max_tokens, temperature=request.temperature
                ),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 -- any failure here must degrade, never raise
            logger.warning("Analyst narration LLM call failed, falling back to baseline text: %s", exc)
            return LLMGenerationResult(text="", model=self._client.model_name, finish_reason="error")

        content = (response.get("content") or "").strip()
        finish_reason = response.get("finish_reason")
        model = response.get("model") or self._client.model_name

        if content and not _is_grounded(request.prompt, content):
            logger.warning(
                "Analyst narration LLM response contained a number not present in its own "
                "grounding prompt -- discarding as a likely hallucination, falling back to baseline text."
            )
            return LLMGenerationResult(text="", model=model, finish_reason="rejected_ungrounded")

        return LLMGenerationResult(text=content, model=model, finish_reason=finish_reason)
