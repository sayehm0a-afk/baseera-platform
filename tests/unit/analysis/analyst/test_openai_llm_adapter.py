"""Unit tests for OpenAILLMAdapter -- a fake OpenAILLMClient stands in
for the real network client (the same technique
tests/unit/news_intelligence/test_analyzer.py already uses); no real
OpenAI call in any test here. Focuses on the three safety properties
the module docstring promises: never raises, falls back to empty text
(never a fabricated fallback) on any failure, and rejects a completion
that introduces a number absent from its own grounding prompt."""

import asyncio

import pytest

from src.analysis.analyst.llm_adapter import LLMGenerationRequest
from src.analysis.analyst.openai_llm_adapter import OpenAILLMAdapter, _is_grounded


class _FakeClient:
    model_name = "gpt-4o-mini"

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = 0
        self.last_kwargs = None

    async def generate_response(self, messages, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        return self._response


def _response(content, model="gpt-4o-mini", finish_reason="stop"):
    return {"content": content, "model": model, "finish_reason": finish_reason}


class TestIsGrounded:
    def test_a_completion_with_no_numbers_is_always_grounded(self):
        assert _is_grounded("RSI is high", "The stock looks strong") is True

    def test_a_completion_reusing_the_prompts_numbers_is_grounded(self):
        prompt = "RSI is 48.45 and the target price is 129.64."
        completion = "With an RSI of 48.45, the target of 129.64 looks reasonable."
        assert _is_grounded(prompt, completion) is True

    def test_a_completion_introducing_a_new_number_is_not_grounded(self):
        prompt = "RSI is 48.45."
        completion = "RSI is 48.45 and the target price is 999.99."
        assert _is_grounded(prompt, completion) is False


class TestOpenAILLMAdapterGenerate:
    @pytest.mark.asyncio
    async def test_returns_the_completion_text_when_grounded(self):
        client = _FakeClient(response=_response("RSI is 48.45, a neutral reading."))
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=5)
        result = await adapter.generate(LLMGenerationRequest(prompt="Rephrase: RSI is 48.45."))
        assert result.text == "RSI is 48.45, a neutral reading."
        assert result.model == "gpt-4o-mini"
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_passes_max_tokens_and_temperature_through(self):
        client = _FakeClient(response=_response("ok"))
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=5)
        await adapter.generate(LLMGenerationRequest(prompt="hi", max_tokens=123, temperature=0.7))
        assert client.last_kwargs["max_tokens"] == 123
        assert client.last_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_includes_a_system_message_only_when_provided(self):
        client = _FakeClient(response=_response("ok"))
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=5)

        await adapter.generate(LLMGenerationRequest(prompt="hi"))
        no_system_call = client.calls

        await adapter.generate(LLMGenerationRequest(prompt="hi", system_prompt="You are an analyst."))
        assert client.calls == no_system_call + 1

    @pytest.mark.asyncio
    async def test_never_raises_on_a_client_exception_and_returns_empty_text(self):
        client = _FakeClient(raises=RuntimeError("network exploded"))
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=5)
        result = await adapter.generate(LLMGenerationRequest(prompt="hi"))
        assert result.text == ""
        assert result.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_never_hangs_past_its_timeout(self):
        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)

        client = _FakeClient()
        client.generate_response = _hang
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=0.05)
        result = await adapter.generate(LLMGenerationRequest(prompt="hi"))
        assert result.text == ""
        assert result.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_rejects_an_ungrounded_completion_and_returns_empty_text(self):
        client = _FakeClient(response=_response("The target price is now 999.99, not what was stated."))
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=5)
        result = await adapter.generate(LLMGenerationRequest(prompt="Rephrase: RSI is 48.45."))
        assert result.text == ""
        assert result.finish_reason == "rejected_ungrounded"

    @pytest.mark.asyncio
    async def test_empty_content_response_is_returned_as_empty_text(self):
        client = _FakeClient(response=_response(""))
        adapter = OpenAILLMAdapter(client=client, timeout_seconds=5)
        result = await adapter.generate(LLMGenerationRequest(prompt="hi"))
        assert result.text == ""
