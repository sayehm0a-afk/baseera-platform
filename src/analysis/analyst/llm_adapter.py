"""LLMAdapter: the Autonomous AI Analyst Framework's sole extension
point for an external language model.

This module intentionally ships **no concrete adapter that calls a
real provider**. `LLMAdapter` is an abstract interface only -- the
architecture `ReasoningPipeline` is built to plug an implementation
into, if and when a future milestone explicitly adds one. Nothing in
this codebase constructs anything other than `NullLLMAdapter` (a
test-only, no-network double proving the extension point works), and
`AnalystEngine`/`ReasoningPipeline` never require an adapter at all --
every explanation this framework produces today is generated entirely
by the deterministic, template-based `NarrativeBuilder` /
`RecommendationComposer` pipeline. This is a hard architectural
boundary, not an oversight: connecting OpenAI, Claude, Gemini, or any
other external AI model is explicitly out of scope for this phase.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMGenerationRequest:
    """One prompt-completion request an `LLMAdapter` implementation
    would receive. `system_prompt` is optional since a deterministic
    template-grounded prompt (see `PromptTemplateManager.build_prompt`)
    is often self-contained."""

    prompt: str
    max_tokens: int = 300
    temperature: float = 0.3
    system_prompt: Optional[str] = None


@dataclass(frozen=True)
class LLMGenerationResult:
    """One completion. `finish_reason` is provider-defined free text
    (e.g. "stop", "length") -- callers should not branch on it beyond
    logging, since no real provider is wired up to define its
    vocabulary yet."""

    text: str
    model: str
    finish_reason: Optional[str] = None


class LLMAdapter(ABC):
    """The interface any future LLM integration must satisfy to plug
    into `ReasoningPipeline` without that pipeline's own code changing.
    Abstract only -- see module docstring for why no concrete,
    network-calling implementation exists in this codebase."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        ...


class NullLLMAdapter(LLMAdapter):
    """A no-op adapter that echoes its prompt back instead of calling
    any model. Exists solely so tests can prove `ReasoningPipeline`
    correctly detects, calls, and consumes the result of an injected
    `LLMAdapter` -- it is never constructed by `AnalystEngine`'s own
    default wiring, and connects to no external service."""

    name = "null"

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        return LLMGenerationResult(text=request.prompt, model="null-adapter", finish_reason="not_implemented")
