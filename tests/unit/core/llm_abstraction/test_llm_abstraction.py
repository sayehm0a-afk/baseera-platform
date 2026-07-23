"""
اختبارات الوحدة لطبقة تجريد نماذج اللغة الكبيرة (LLM Abstraction Layer).
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import os
from typing import List, Dict, Any

from src.core.llm_abstraction.base_llm_client import BaseLLMClient
from src.core.llm_abstraction.openai_llm_client import OpenAILLMClient

# Mock the tiktoken import for environments where it might not be installed


class MockEncoding:
    def encode(self, text: str) -> List[int]:
        return [1] * 5


class MockTiktoken:
    def encoding_for_model(self, model_name: str):
        return MockEncoding()


@pytest.fixture(autouse=True)
def mock_tiktoken_import():
    with patch.dict("sys.modules", {"tiktoken": MockTiktoken()}):
        yield


@pytest.fixture
def openai_api_key():
    os.environ["OPENAI_API_KEY"] = "test_api_key"
    yield
    del os.environ["OPENAI_API_KEY"]


@pytest.mark.asyncio
async def test_base_llm_client_initialization():
    class ConcreteLLMClient(BaseLLMClient):
        async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
            pass

        async def count_tokens(self, text: str) -> int:
            pass

        async def get_model_info(self) -> Dict[str, Any]:
            pass

    client = ConcreteLLMClient(model_name="test-model", config={"temp": 0.7})
    assert client.model_name == "test-model"
    assert client.config["temp"] == 0.7


@pytest.mark.asyncio
async def test_base_llm_client_handle_retry_success():
    class ConcreteLLMClient(BaseLLMClient):
        async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
            pass

        async def count_tokens(self, text: str) -> int:
            pass

        async def get_model_info(self) -> Dict[str, Any]:
            pass

    client = ConcreteLLMClient(model_name="test-model", config={"max_retries": 3, "retry_delay": 0.01})
    mock_func = AsyncMock(return_value="success")
    result = await client._handle_retry(mock_func, "arg1", kwarg1="value1")
    assert result == "success"
    mock_func.assert_called_once_with("arg1", kwarg1="value1")


@pytest.mark.asyncio
async def test_base_llm_client_handle_retry_failure():
    class ConcreteLLMClient(BaseLLMClient):
        async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
            pass

        async def count_tokens(self, text: str) -> int:
            pass

        async def get_model_info(self) -> Dict[str, Any]:
            pass

    client = ConcreteLLMClient(model_name="test-model", config={"max_retries": 3, "retry_delay": 0.01})
    mock_func = AsyncMock(side_effect=[Exception("fail"), Exception("fail"), "success"])
    result = await client._handle_retry(mock_func, "arg1")
    assert result == "success"
    assert mock_func.call_count == 3


@pytest.mark.asyncio
async def test_base_llm_client_handle_retry_exhausted():
    class ConcreteLLMClient(BaseLLMClient):
        async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
            pass

        async def count_tokens(self, text: str) -> int:
            pass

        async def get_model_info(self) -> Dict[str, Any]:
            pass

    client = ConcreteLLMClient(model_name="test-model", config={"max_retries": 2, "retry_delay": 0.01})
    mock_func = AsyncMock(side_effect=[Exception("fail"), Exception("fail"), Exception("fail")])
    with pytest.raises(Exception, match="fail"):
        await client._handle_retry(mock_func, "arg1")
    assert mock_func.call_count == 2


def test_openai_llm_client_initialization_no_api_key():
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    with pytest.raises(ValueError, match="OPENAI_API_KEY environment variable not set."):
        OpenAILLMClient(model_name="gpt-3.5-turbo")


def test_openai_llm_client_initialization_with_api_key(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    assert client.model_name == "gpt-3.5-turbo"
    assert client.api_key == "test_api_key"
    assert client.client is not None


@pytest.mark.asyncio
async def test_openai_llm_client_generate_response(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    mock_create = AsyncMock()
    mock_create.return_value.choices = [AsyncMock()]
    mock_create.return_value.choices[0].message.content = "Hello from OpenAI"
    mock_create.return_value.choices[0].message.role = "assistant"
    mock_create.return_value.choices[0].finish_reason = "stop"
    from unittest.mock import MagicMock
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
async def test_openai_llm_client_count_tokens(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    text = "هذا نص تجريبي لحساب التوكنات."
    with patch("src.core.llm_abstraction.openai_llm_client._tiktoken", new=MockTiktoken()):
        tokens = await client.count_tokens(text)
        assert tokens == 5


@pytest.mark.asyncio
async def test_openai_llm_client_get_model_info(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    info = await client.get_model_info()
    assert info["model_name"] == "gpt-3.5-turbo"
    assert info["provider"] == "OpenAI"
    assert "pricing_input_per_1k_tokens" in info


@pytest.mark.asyncio
async def test_openai_llm_client_generate_response_error(openai_api_key):
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    mock_create = AsyncMock(side_effect=Exception("API Error"))
    with patch.object(client.client.chat.completions, "create", new=mock_create):
        messages = [{"role": "user", "content": "Test"}]
        with pytest.raises(Exception, match="API Error"):
            await client.generate_response(messages)


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
