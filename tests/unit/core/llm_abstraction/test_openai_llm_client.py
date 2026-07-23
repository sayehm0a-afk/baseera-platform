"""
اختبارات الوحدة لعميل OpenAI LLM.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import os
import sys
# Pre-existing hardcoded path from an earlier dev environment; left as-is
# (out of M1.5 lint-debt scope) -- imports below are noqa'd rather than
# reordered so this fix carries zero behavior-change risk.
sys.path.insert(0, '/home/ubuntu/basirah')
from typing import List, Dict, Any  # noqa: E402

from src.core.llm_abstraction.openai_llm_client import OpenAILLMClient, _tiktoken  # noqa: E402

# Mock the tiktoken import for environments where it might not be installed


@pytest.fixture
def mock_tiktoken_module():
    with patch("src.core.llm_abstraction.openai_llm_client._tiktoken", new_callable=MagicMock) as mock_tiktoken_module:
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2, 3, 4, 5]  # Simulate 5 tokens
        mock_tiktoken_module.encoding_for_model.return_value = mock_encoder
        yield mock_tiktoken_module


@pytest.fixture
def openai_api_key():
    os.environ["OPENAI_API_KEY"] = "test_api_key"
    yield
    del os.environ["OPENAI_API_KEY"]


@pytest.mark.asyncio
async def test_openai_llm_client_initialization_no_api_key():
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    with pytest.raises(ValueError, match="OPENAI_API_KEY environment variable not set."):
        OpenAILLMClient(model_name="gpt-3.5-turbo")


@pytest.mark.asyncio
async def test_openai_llm_client_initialization_with_api_key(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    assert client.model_name == "gpt-3.5-turbo"
    assert client.api_key == "test_api_key"
    assert client.client is not None


@pytest.mark.asyncio
async def test_openai_llm_client_generate_response_success(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    mock_create = AsyncMock()
    mock_create.return_value.choices = [MagicMock()]
    mock_create.return_value.choices[0].message.content = "Hello from OpenAI"
    mock_create.return_value.choices[0].message.role = "assistant"
    mock_create.return_value.choices[0].finish_reason = "stop"
    mock_create.return_value.usage = MagicMock()
    mock_create.return_value.usage.model_dump.return_value = {"prompt_tokens": 10, "completion_tokens": 5}
    mock_create.return_value.model = "gpt-3.5-turbo"

    with patch.object(client.client.chat.completions, "create", new=mock_create):
        messages = [{"role": "user", "content": "Test"}]
        response = await client.generate_response(messages)
        assert response["content"] == "Hello from OpenAI"
        assert response["role"] == "assistant"
        assert response["finish_reason"] == "stop"
        assert response["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
        assert response["model"] == "gpt-3.5-turbo"
        mock_create.assert_called_once_with(model="gpt-3.5-turbo", messages=messages)


@pytest.mark.asyncio
async def test_openai_llm_client_generate_response_no_choices(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    mock_create = AsyncMock()
    mock_create.return_value.choices = []
    mock_create.return_value.usage = None
    mock_create.return_value.model = "gpt-3.5-turbo"

    with patch.object(client.client.chat.completions, "create", new=mock_create):
        messages = [{"role": "user", "content": "Test"}]
        response = await client.generate_response(messages)
        assert response["content"] == ""
        assert response["role"] == "assistant"
        assert response["finish_reason"] == "no_response"
        assert "usage" not in response
        assert "model" not in response


@pytest.mark.asyncio
async def test_openai_llm_client_generate_response_error(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    mock_create = AsyncMock(side_effect=Exception("API Error"))
    with patch.object(client.client.chat.completions, "create", new=mock_create):
        messages = [{"role": "user", "content": "Test"}]
        with pytest.raises(Exception, match="API Error"):
            await client.generate_response(messages)


@pytest.mark.asyncio
async def test_openai_llm_client_count_tokens_with_tiktoken(openai_api_key, mock_tiktoken_module):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    text = "هذا نص تجريبي لحساب التوكنات."
    tokens = await client.count_tokens(text)
    assert tokens == 5
    mock_tiktoken_module.encoding_for_model.assert_called_once_with(client.model_name)
    mock_tiktoken_module.encoding_for_model.return_value.encode.assert_called_once_with(text)


@pytest.mark.asyncio
async def test_openai_llm_client_count_tokens_no_tiktoken(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    text = "هذا نص تجريبي لحساب التوكنات."
    with patch("src.core.llm_abstraction.openai_llm_client._tiktoken", new=None):
        tokens = await client.count_tokens(text)
        assert tokens == 6  # Rough estimate: len(text.split()) * 4 // 3 for "هذا نص تجريبي لحساب التوكنات." is 6
        # The warning message is logged when tiktoken is None, so no call to encoding_for_model
        # No assertion for encoding_for_model as it should not be called when tiktoken is None.


@pytest.mark.asyncio
async def test_openai_llm_client_get_model_info(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    info = await client.get_model_info()
    assert info["model_name"] == "gpt-3.5-turbo"
    assert info["provider"] == "OpenAI"
    assert "pricing_input_per_1k_tokens" in info


@pytest.mark.asyncio
async def test_openai_llm_client_get_model_info_gpt4(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-4")
    info = await client.get_model_info()
    assert info["model_name"] == "gpt-4"
    assert info["pricing_input_per_1k_tokens"] == 0.03


@pytest.mark.asyncio
async def test_openai_llm_client_get_model_info_gpt35(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo-0125")
    info = await client.get_model_info()
    assert info["model_name"] == "gpt-3.5-turbo-0125"
    assert info["pricing_input_per_1k_tokens"] == 0.0005


@pytest.mark.asyncio
async def test_openai_llm_client_handle_retry_success(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo", config={"max_retries": 3, "retry_delay": 0.01})
    mock_func = AsyncMock(return_value="success")
    result = await client._handle_retry(mock_func, "arg1", kwarg1="value1")
    assert result == "success"
    mock_func.assert_called_once_with("arg1", kwarg1="value1")


@pytest.mark.asyncio
async def test_openai_llm_client_handle_retry_failure(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo", config={"max_retries": 3, "retry_delay": 0.01})
    mock_func = AsyncMock(side_effect=[Exception("fail"), Exception("fail"), "success"])
    result = await client._handle_retry(mock_func, "arg1")
    assert result == "success"
    assert mock_func.call_count == 3


@pytest.mark.asyncio
async def test_openai_llm_client_handle_retry_exhausted(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo", config={"max_retries": 2, "retry_delay": 0.01})
    mock_func = AsyncMock(side_effect=[Exception("fail"), Exception("fail"), Exception("fail")])
    with pytest.raises(Exception, match="fail"):
        await client._handle_retry(mock_func, "arg1")
        assert mock_func.call_count == 2
