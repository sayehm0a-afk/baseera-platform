import pytest
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from src.core.base_agent.base_agent import BaseAgent

# Mock logging to prevent console output during tests


@pytest.fixture(autouse=True)
def no_logging(caplog):
    caplog.set_level(logging.CRITICAL)


def test_base_agent_initialization():
    agent = BaseAgent(name="TestAgent", description="A test agent")
    assert agent.name == "TestAgent"
    assert agent.description == "A test agent"
    assert agent.status == "initialized"
    assert isinstance(agent.agent_id, str)
    assert isinstance(agent.created_at, datetime)
    assert agent.memory == {}
    assert agent.tools == {}
    assert agent.llm_client is None


def test_base_agent_custom_id_initialization():
    agent = BaseAgent(agent_id="custom-id-123")
    assert agent.agent_id == "custom-id-123"


@pytest.mark.asyncio
async def test_base_agent_activate_success():
    agent = BaseAgent()
    with patch.object(agent, '_load_config') as mock_load_config:
        with patch.object(agent, '_initialize_memory') as mock_init_memory:
            with patch.object(agent, '_initialize_tools', new_callable=pytest.MonkeyPatch) as mock_init_tools:
                # We need to mock the async method properly
                async def mock_async_init_tools(*args, **kwargs):
                    pass
                agent._initialize_tools = mock_async_init_tools
                with patch.object(agent, '_initialize_llm_client', new_callable=AsyncMock) as mock_init_llm_client:

                    assert await agent.activate() is True
                    assert agent.status == "active"
                    mock_load_config.assert_called_once()
                    mock_init_memory.assert_called_once()
                    mock_init_llm_client.assert_called_once()


@pytest.mark.asyncio
async def test_base_agent_activate_from_paused():
    agent = BaseAgent()
    agent.status = "paused"

    async def mock_async_init_tools(*args, **kwargs):
        pass
    agent._initialize_tools = mock_async_init_tools
    assert await agent.activate() is True
    assert agent.status == "active"


@pytest.mark.asyncio
async def test_base_agent_activate_when_active():
    agent = BaseAgent()
    agent.status = "active"
    assert await agent.activate() is False
    assert agent.status == "active"


def test_base_agent_pause_success():
    agent = BaseAgent()
    agent.status = "active"
    assert agent.pause() is True
    assert agent.status == "paused"


def test_base_agent_pause_when_not_active():
    agent = BaseAgent()
    assert agent.pause() is False
    assert agent.status == "initialized"


def test_base_agent_terminate_success():
    agent = BaseAgent()
    assert agent.terminate() is True
    assert agent.status == "terminated"


def test_base_agent_terminate_when_already_terminated():
    agent = BaseAgent()
    agent.status = "terminated"
    assert agent.terminate() is False
    assert agent.status == "terminated"


@pytest.mark.asyncio
async def test_base_agent_process_task_not_implemented():
    agent = BaseAgent()

    async def mock_async_init_tools(*args, **kwargs):
        pass
    agent._initialize_tools = mock_async_init_tools
    await agent.activate()
    with pytest.raises(NotImplementedError, match="process_task method must be implemented by subclasses"):
        agent.process_task({"task_id": "1"})


def test_base_agent_process_task_not_active():
    agent = BaseAgent()
    with pytest.raises(RuntimeError, match="Agent not active"):
        agent.process_task({"task_id": "1"})


@pytest.mark.asyncio
async def test_base_agent_get_status():
    agent = BaseAgent()
    assert agent.get_status() == "initialized"

    async def mock_async_init_tools(*args, **kwargs):
        pass
    agent._initialize_tools = mock_async_init_tools
    await agent.activate()
    assert agent.get_status() == "active"


def test_base_agent_get_info():
    agent = BaseAgent(name="InfoAgent", description="Agent for info")
    info = agent.get_info()
    assert info["name"] == "InfoAgent"
    assert info["description"] == "Agent for info"
    assert info["status"] == "initialized"
    assert "agent_id" in info
    assert "created_at" in info
    assert info["memory_keys"] == []
    assert info["available_tools"] == []


def test_base_agent_reason_placeholder():
    agent = BaseAgent()
    result = agent._reason("test prompt", {"key": "value"})
    assert result == "Reasoning result"


@pytest.mark.asyncio
async def test_base_agent_call_tool_no_registry():
    agent = BaseAgent()
    with pytest.raises(RuntimeError, match="ToolRegistry not initialized for this agent"):
        await agent._call_tool("test_tool")


@pytest.mark.asyncio
async def test_base_agent_call_tool_not_found():
    agent = BaseAgent()
    from unittest.mock import AsyncMock
    agent.tool_registry = MagicMock()
    agent.tool_registry.get_tool = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="Tool non_existent_tool not found in registry"):
        await agent._call_tool("non_existent_tool")


@pytest.mark.asyncio
async def test_base_agent_call_tool_success():
    agent = BaseAgent()
    from unittest.mock import AsyncMock
    agent.tool_registry = MagicMock()
    mock_tool = AsyncMock()
    mock_tool.execute = AsyncMock(return_value="Result from test_tool")
    agent.tool_registry.get_tool = AsyncMock(return_value=mock_tool)

    result = await agent._call_tool("test_tool", arg1="val1")
    assert result == "Result from test_tool"
    mock_tool.execute.assert_called_once_with(arg1="val1")


@pytest.mark.asyncio
async def test_base_agent_initialize_tools_no_registry():
    agent = BaseAgent()
    await agent._initialize_tools()
    assert agent.tool_registry is None
    assert agent.tools == {}


@pytest.mark.asyncio
async def test_base_agent_initialize_tools_with_registry():
    agent = BaseAgent()
    from unittest.mock import AsyncMock
    mock_registry = MagicMock()
    mock_registry.get_all_tools = AsyncMock(return_value={"tool1": "mock_tool_1"})
    await agent._initialize_tools(mock_registry)
    assert agent.tool_registry == mock_registry
    assert agent.tools == {"tool1": "mock_tool_1"}


@pytest.mark.asyncio
async def test_base_agent_interact_with_llm_placeholder():
    agent = BaseAgent()
    from unittest.mock import AsyncMock
    agent.llm_client = AsyncMock()
    agent.llm_client.generate_text.return_value = "LLM response"
    messages = [{'role': 'user', 'content': 'hello'}]
    result = await agent._interact_with_llm(messages)
    agent.llm_client.generate_text.assert_called_once_with(messages, "default")
    assert result == "LLM response"


@pytest.mark.asyncio
async def test_base_agent_interact_with_llm_no_client():
    agent = BaseAgent()
    messages = [{'role': 'user', 'content': 'hello'}]
    with pytest.raises(RuntimeError, match="LLM client not available"):
        await agent._interact_with_llm(messages)
