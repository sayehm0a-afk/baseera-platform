"""OpenAIBasirahBrainProvider: the real, network-calling provider for
Stage 1. Reuses the existing, already-production-tested
`OpenAILLMClient` (src/core/llm_abstraction/openai_llm_client.py) --
the same client `NewsAnalyzer` and `OpenAILLMAdapter` already call in
production -- so this introduces no new provider integration, only a
new caller of infrastructure that already exists.

The runtime model provider is a product architecture decision, not tied
to whichever assistant wrote this code -- per the mandate's explicit
instruction, no Anthropic/Claude client is introduced here; OpenAI is
reused because it is what this repository already has a tested adapter
for.

Uses OpenAI's JSON-mode `response_format={"type": "json_object"}` (the
API-level structured-output constraint, broadly supported across the
gpt-4o family) plus strict Pydantic validation of the result -- belt and
suspenders, since JSON mode alone only guarantees syntactically valid
JSON, not schema conformance. `temperature` is low and a `seed` is
passed when configured, for the most reproducible generation this API
surface allows; note that OpenAI's `seed` parameter is documented as
best-effort, not a hard determinism guarantee.

`analyze()` never raises for an ordinary failure -- see provider.py's
module docstring for the contract every implementation must satisfy.

Pre-merge hardening audit (Finding F4): when this provider constructs
its OWN `OpenAILLMClient` (the `client=None` default path -- never when
a caller injects its own client, e.g. in tests), it passes an explicit,
local `config={"max_retries": ...}` so `OpenAILLMClient._handle_retry`'s
own internal retry loop is bounded to exactly
`get_basirah_brain_max_provider_call_attempts()` (default 1) real calls
per `generate_response()` invocation -- i.e. per `analyze()` call. This
does NOT change `OpenAILLMClient`'s shared, global default (still 3 for
every other caller, e.g. NewsAnalyzer/OpenAILLMAdapter) -- only this
provider's own instance is configured differently, via the same
`config=` override point that class already exposes.
"""

import json
import logging
import time
from typing import Optional

from src.core.llm_abstraction.openai_llm_client import OpenAILLMClient

from ..config import (
    get_basirah_brain_max_output_tokens,
    get_basirah_brain_max_provider_call_attempts,
    get_basirah_brain_model_name,
    get_basirah_brain_seed,
    get_basirah_brain_temperature,
    get_basirah_brain_timeout_seconds,
)
from ..prompts import build_system_prompt, build_user_prompt
from ..provider import BasirahBrainProviderOutcome
from ..schemas import BasirahBrainDecisionV1, BasirahBrainInputV1

logger = logging.getLogger(__name__)


class OpenAIBasirahBrainProvider:
    """Concrete `BasirahBrainProvider` backed by OpenAI's chat-completions
    API via the shared `OpenAILLMClient`."""

    def __init__(self, client: Optional[OpenAILLMClient] = None, timeout_seconds: Optional[float] = None):
        self._client = client or OpenAILLMClient(
            model_name=get_basirah_brain_model_name(),
            config={"max_retries": get_basirah_brain_max_provider_call_attempts()},
        )
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else get_basirah_brain_timeout_seconds()
        )
        self._system_prompt = build_system_prompt()

    async def analyze(self, brain_input: BasirahBrainInputV1) -> BasirahBrainProviderOutcome:
        import asyncio

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": build_user_prompt(brain_input)},
        ]

        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.generate_response(
                    messages,
                    max_tokens=get_basirah_brain_max_output_tokens(),
                    temperature=get_basirah_brain_temperature(),
                    seed=get_basirah_brain_seed(),
                    response_format={"type": "json_object"},
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Basirah Brain provider call timed out after %.1fs.", self._timeout_seconds)
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=None,
                error_code="PROVIDER_TIMEOUT",
                model_provider="openai",
                model_name=self._client.model_name,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001 -- any provider failure must degrade, never raise
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Basirah Brain provider call failed: %s", exc)
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=None,
                error_code=f"PROVIDER_EXCEPTION:{type(exc).__name__}",
                model_provider="openai",
                model_name=self._client.model_name,
                latency_ms=latency_ms,
            )
        latency_ms = (time.monotonic() - start) * 1000

        content = (response.get("content") or "").strip()
        usage = response.get("usage") or {}
        model_name = response.get("model") or self._client.model_name

        if not content:
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=content,
                error_code="EMPTY_RESPONSE",
                model_provider="openai",
                model_name=model_name,
                latency_ms=latency_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Basirah Brain provider returned invalid JSON -- failing closed.")
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=content,
                error_code="INVALID_JSON",
                model_provider="openai",
                model_name=model_name,
                latency_ms=latency_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )

        try:
            decision = BasirahBrainDecisionV1.model_validate(parsed)
        except Exception:  # noqa: BLE001 -- pydantic ValidationError, fail closed
            logger.warning("Basirah Brain provider output failed schema validation -- failing closed.")
            return BasirahBrainProviderOutcome(
                success=False,
                decision=None,
                raw_content=content,
                error_code="SCHEMA_VALIDATION_FAILED",
                model_provider="openai",
                model_name=model_name,
                latency_ms=latency_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )

        return BasirahBrainProviderOutcome(
            success=True,
            decision=decision,
            raw_content=content,
            error_code=None,
            model_provider="openai",
            model_name=model_name,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
