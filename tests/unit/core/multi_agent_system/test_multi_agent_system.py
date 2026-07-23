"""
اختبارات الوحدة لنظام العملاء المتعددين (Multi-Agent System).
"""
import pytest
import logging
import re
from unittest.mock import AsyncMock, MagicMock
from typing import Any

from src.core.multi_agent_system.supervisor_agent import SupervisorAgent
from src.core.multi_agent_system.agent_registry import AgentRegistry
from src.core.multi_agent_system.base_tool import BaseTool
from src.core.multi_agent_system.tool_registry import ToolRegistry
from src.core.base_agent.base_agent import BaseAgent


class _TestTool(BaseTool):
    async def execute(self, **kwargs) -> Any:
        return f"TestTool executed with {kwargs}"

# Fixtures for AgentRegistry and ToolRegistry


@pytest.fixture
def agent_registry():
    return AgentRegistry()


@pytest.fixture
def tool_registry():
    return ToolRegistry()

# Fixture for a mock tool


@pytest.fixture
def mock_tool():
    tool = _TestTool(name="test_tool", description="A simple test tool", parameters={"param1": "str"})
    tool.execute = AsyncMock(return_value="tool_executed")
    return tool

# Fixture for a mock agent


@pytest.fixture
def mock_agent():
    agent = MagicMock(spec=BaseAgent)
    agent.agent_id = "agent123"
    agent.name = "TestAgent"
    agent.description = "A simple test agent"
    agent.process_task = AsyncMock(return_value={"status": "task_processed"})
    return agent


@pytest.mark.asyncio
async def test_agent_registry_initialization():
    registry = AgentRegistry()
    assert isinstance(registry._agents, dict)
    assert len(registry._agents) == 0


@pytest.mark.asyncio
async def test_agent_registry_register_agent(agent_registry, mock_agent):
    result = await agent_registry.register_agent(mock_agent)
    assert result is True
    assert agent_registry._agents["agent123"] == mock_agent


@pytest.mark.asyncio
async def test_agent_registry_register_agent_already_registered(agent_registry, mock_agent):
    await agent_registry.register_agent(mock_agent)
    result = await agent_registry.register_agent(mock_agent)
    assert result is False


@pytest.mark.asyncio
async def test_agent_registry_unregister_agent(agent_registry, mock_agent):
    await agent_registry.register_agent(mock_agent)
    result = await agent_registry.unregister_agent("agent123")
    assert result is True
    assert "agent123" not in agent_registry._agents


@pytest.mark.asyncio
async def test_agent_registry_unregister_agent_not_found(agent_registry):
    result = await agent_registry.unregister_agent("non_existent_agent")
    assert result is False


@pytest.mark.asyncio
async def test_agent_registry_get_agent(agent_registry, mock_agent):
    await agent_registry.register_agent(mock_agent)
    retrieved_agent = await agent_registry.get_agent("agent123")
    assert retrieved_agent == mock_agent


@pytest.mark.asyncio
async def test_agent_registry_get_agent_not_found(agent_registry):
    retrieved_agent = await agent_registry.get_agent("non_existent_agent")
    assert retrieved_agent is None


@pytest.mark.asyncio
async def test_agent_registry_get_all_agents(agent_registry, mock_agent):
    await agent_registry.register_agent(mock_agent)
    all_agents = await agent_registry.get_all_agents()
    assert all_agents == {"agent123": mock_agent}


@pytest.mark.asyncio
async def test_agent_registry_get_agents_by_name(agent_registry, mock_agent):
    await agent_registry.register_agent(mock_agent)
    agents_by_name = await agent_registry.get_agents_by_name("TestAgent")
    assert agents_by_name == [mock_agent]


@pytest.mark.asyncio
async def test_agent_registry_get_agents_by_description_keyword(agent_registry, mock_agent):
    await agent_registry.register_agent(mock_agent)
    agents_by_keyword = await agent_registry.get_agents_by_description_keyword("test")
    assert agents_by_keyword == [mock_agent]


@pytest.mark.asyncio
async def test_tool_registry_initialization():
    registry = ToolRegistry()
    assert isinstance(registry._tools, dict)
    assert len(registry._tools) == 0


@pytest.mark.asyncio
async def test_tool_registry_register_tool(tool_registry, mock_tool):
    result = await tool_registry.register_tool(mock_tool)
    assert result is True
    assert tool_registry._tools["test_tool"] == mock_tool


@pytest.mark.asyncio
async def test_tool_registry_register_tool_already_registered(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    result = await tool_registry.register_tool(mock_tool)
    assert result is False


@pytest.mark.asyncio
async def test_tool_registry_unregister_tool(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    result = await tool_registry.unregister_tool("test_tool")
    assert result is True
    assert "test_tool" not in tool_registry._tools


@pytest.mark.asyncio
async def test_tool_registry_unregister_tool_not_found(tool_registry):
    result = await tool_registry.unregister_tool("non_existent_tool")
    assert result is False


@pytest.mark.asyncio
async def test_tool_registry_get_tool(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    retrieved_tool = await tool_registry.get_tool("test_tool")
    assert retrieved_tool == mock_tool


@pytest.mark.asyncio
async def test_tool_registry_get_tool_not_found(tool_registry):
    retrieved_tool = await tool_registry.get_tool("non_existent_tool")
    assert retrieved_tool is None


@pytest.mark.asyncio
async def test_tool_registry_get_all_tools(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    all_tools = await tool_registry.get_all_tools()
    assert all_tools == {"test_tool": mock_tool}


@pytest.mark.asyncio
async def test_tool_registry_get_tools_by_keyword(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    tools_by_keyword = await tool_registry.get_tools_by_keyword("test")
    assert tools_by_keyword == [mock_tool]


@pytest.mark.asyncio
async def test_base_tool_initialization():
    tool = _TestTool(name="my_tool", description="My tool description")
    assert tool.name == "my_tool"
    assert tool.description == "My tool description"
    assert tool.parameters == {}


@pytest.mark.asyncio
async def test_base_tool_get_info():
    tool = _TestTool(name="my_tool", description="My tool description", parameters={"param": "value"})
    info = tool.get_info()
    assert info == {"name": "my_tool", "description": "My tool description", "parameters": {"param": "value"}}


@pytest.mark.asyncio
async def test_base_tool_execute_implemented():
    tool = _TestTool(name="my_tool", description="My tool description")
    result = await tool.execute(arg="value")
    assert result == "TestTool executed with {'arg': 'value'}"


@pytest.mark.asyncio
async def test_supervisor_agent_initialization(agent_registry):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    assert supervisor.name == "SupervisorAgent"
    assert supervisor.agent_registry == agent_registry


@pytest.mark.asyncio
async def test_supervisor_agent_register_agent(agent_registry, mock_agent):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    result = await supervisor.register_agent(mock_agent)
    assert result is True
    assert await agent_registry.get_agent(mock_agent.agent_id) == mock_agent


@pytest.mark.asyncio
async def test_supervisor_agent_unregister_agent(agent_registry, mock_agent):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    await supervisor.register_agent(mock_agent)
    result = await supervisor.unregister_agent(mock_agent.agent_id)
    assert result is True
    assert await agent_registry.get_agent(mock_agent.agent_id) is None


@pytest.mark.asyncio
async def test_supervisor_agent_get_registered_agents(agent_registry, mock_agent):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    await supervisor.register_agent(mock_agent)
    agents = await supervisor.get_registered_agents()
    assert agents == {mock_agent.agent_id: mock_agent}


@pytest.mark.asyncio
async def test_supervisor_agent_send_message_success(agent_registry, mock_agent):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    await supervisor.register_agent(mock_agent)
    message = {"type": "command", "content": "do_something"}
    result = await supervisor.send_message("sender123", mock_agent.agent_id, message)
    assert result is True
    # The mock agent's process_task is not called here, as send_message only simulates delivery


@pytest.mark.asyncio
async def test_supervisor_agent_send_message_receiver_not_found(agent_registry):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    message = {"type": "command", "content": "do_something"}
    result = await supervisor.send_message("sender123", "non_existent_agent", message)
    assert result is False


@pytest.mark.asyncio
async def test_supervisor_agent_process_task_delegation_success(agent_registry, mock_agent):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    await supervisor.register_agent(mock_agent)
    task_data = {"task_id": "task456", "target_agent_id": mock_agent.agent_id, "instruction": "analyze_data"}
    result = await supervisor.process_task(task_data)
    assert result == {"status": "task_processed"}
    mock_agent.process_task.assert_called_once_with(task_data)


@pytest.mark.asyncio
async def test_supervisor_agent_process_task_delegation_agent_not_found(agent_registry):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    task_data = {"task_id": "task456", "target_agent_id": "non_existent_agent", "instruction": "analyze_data"}
    with pytest.raises(ValueError, match="Target agent non_existent_agent not found"):
        await supervisor.process_task(task_data)


@pytest.mark.asyncio
async def test_supervisor_agent_process_task_no_target_agent_id(agent_registry):
    supervisor = SupervisorAgent(agent_registry=agent_registry)
    task_data = {"task_id": "task789", "instruction": "internal_task"}
    result = await supervisor.process_task(task_data)
    assert result == {"status": "completed", "message": "Task handled by Supervisor internally"}


@pytest.mark.asyncio
async def test_base_agent_activate_with_tool_registry(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    agent = BaseAgent(name="TestAgent")
    await agent.activate(tool_registry=tool_registry)
    assert agent.status == "active"
    assert "test_tool" in agent.tools
    assert agent.tools["test_tool"] == mock_tool


@pytest.mark.asyncio
async def test_base_agent_call_tool_success(tool_registry, mock_tool):
    await tool_registry.register_tool(mock_tool)
    agent = BaseAgent(name="TestAgent")
    await agent.activate(tool_registry=tool_registry)
    result = await agent._call_tool("test_tool", param1="value1")
    assert result == "tool_executed"
    mock_tool.execute.assert_called_once_with(param1="value1")


@pytest.mark.asyncio
async def test_base_agent_call_tool_not_found(tool_registry):
    agent = BaseAgent(name="TestAgent")
    await agent.activate(tool_registry=tool_registry)
    with pytest.raises(ValueError, match="Tool non_existent_tool not found in registry"):
        await agent._call_tool("non_existent_tool")


@pytest.mark.asyncio
async def test_base_agent_call_tool_no_tool_registry():
    agent = BaseAgent(name="TestAgent")
    # Do not activate with tool_registry
    with pytest.raises(RuntimeError, match="ToolRegistry not initialized for this agent"):
        await agent._call_tool("any_tool")


@pytest.mark.asyncio
async def test_supervisor_agent_register_agent_no_registry(caplog):
    """Test register_agent when agent_registry is not initialized."""
    supervisor = SupervisorAgent()
    mock_agent = MagicMock(spec=BaseAgent)
    mock_agent.agent_id = "agent123"
    with caplog.at_level(logging.WARNING):
        result = await supervisor.register_agent(mock_agent)
        assert result is False
        assert "Agent registry not initialized for SupervisorAgent SupervisorAgent." in caplog.text


@pytest.mark.asyncio
async def test_supervisor_agent_unregister_agent_no_registry(caplog):
    """Test unregister_agent when agent_registry is not initialized."""
    supervisor = SupervisorAgent()
    with caplog.at_level(logging.WARNING):
        result = await supervisor.unregister_agent("agent123")
        assert result is False
        assert "Agent registry not initialized for SupervisorAgent SupervisorAgent." in caplog.text


@pytest.mark.asyncio
async def test_supervisor_agent_get_registered_agents_no_registry(caplog):
    """Test get_registered_agents when agent_registry is not initialized."""
    supervisor = SupervisorAgent()
    with caplog.at_level(logging.WARNING):
        result = await supervisor.get_registered_agents()
        assert result == {}
        assert "Agent registry not initialized for SupervisorAgent SupervisorAgent." in caplog.text


@pytest.mark.asyncio
async def test_supervisor_agent_initialize_llm_client_logging(caplog):
    """Test _initialize_llm_client logs the correct message."""
    with caplog.at_level(logging.INFO):
        SupervisorAgent()
        # Check if the specific log message from SupervisorAgent's _initialize_llm_client is present
        found_log = False
        for record in caplog.records:
               if record.name == "src.core.multi_agent_system.supervisor_agent" and \
               re.match(r"LLM client for SupervisorAgent .* set to None \(or specialized later\).", record.message):
                found_log = True
                break
        assert found_log, "Expected log message from SupervisorAgent not found."  # pylint: disable=C0301
