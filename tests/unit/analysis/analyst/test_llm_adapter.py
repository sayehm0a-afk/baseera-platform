"""Unit tests for the LLMAdapter extension point. LLMAdapter itself is
abstract -- these tests exercise only NullLLMAdapter, the no-network
test double that proves the interface shape works, never a real
provider."""

import pytest

from src.analysis.analyst.llm_adapter import LLMAdapter, LLMGenerationRequest, NullLLMAdapter


def test_llm_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LLMAdapter()


def test_null_llm_adapter_has_a_name():
    assert NullLLMAdapter().name == "null"


@pytest.mark.asyncio
async def test_null_llm_adapter_echoes_the_prompt_back():
    adapter = NullLLMAdapter()
    result = await adapter.generate(LLMGenerationRequest(prompt="Summarize this."))
    assert result.text == "Summarize this."
    assert result.model == "null-adapter"
    assert result.finish_reason == "not_implemented"


def test_generation_request_defaults():
    request = LLMGenerationRequest(prompt="hello")
    assert request.max_tokens == 300
    assert request.temperature == 0.3
    assert request.system_prompt is None
