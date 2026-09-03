"""Provider abstraction for Basirah Brain -- the sole extension point
for whichever model actually performs the synthesis. Two implementations
ship with Stage 1: `MockBasirahBrainProvider` (no network, deterministic,
used by every test and safe for local development) and
`OpenAIBasirahBrainProvider` (reuses the existing, already-production-
tested `OpenAILLMClient`).

`BasirahBrainProviderOutcome` is a typed, always-safe result: a provider
implementation must never raise out of `analyze()` for an ordinary
failure (timeout, malformed JSON, provider error) -- it catches those
itself and returns `success=False` with a `raw_content`/`error_code`
that `service.py` records for the audit trail. Only a genuine
programming error should propagate as an exception.
"""

from dataclasses import dataclass
from typing import Optional, Protocol

from .schemas import BasirahBrainDecisionV1, BasirahBrainInputV1


@dataclass(frozen=True)
class BasirahBrainProviderOutcome:
    success: bool
    decision: Optional[BasirahBrainDecisionV1]
    raw_content: Optional[str]
    error_code: Optional[str]
    model_provider: str
    model_name: str
    latency_ms: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class BasirahBrainProvider(Protocol):
    async def analyze(self, brain_input: BasirahBrainInputV1) -> BasirahBrainProviderOutcome:
        ...
