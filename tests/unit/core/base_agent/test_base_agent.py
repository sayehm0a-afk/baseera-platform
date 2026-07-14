import pytest
import logging
from unittest.mock import MagicMock, patch
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

def test_base_agent_activate_success():
    agent = BaseAgent()
    with patch.object(agent, '_load_config') as mock_load_config:
        with patch.object(agent, '_initialize_memory') as mock_init_memory:
            with patch.object(agent, '_initialize_tools') as mock_init_tools:
                with patch.object(agent, '_initialize_llm_client') as mock_init_llm_client:
                    assert agent.activate() is True
                    assert agent.status == "active"
                    mock_load_config.assert_called_once()
                    mock_init_memory.assert_called_once()
                    mock_init_tools.assert_called_once()
                    mock_init_llm_client.assert_called_once()

def test_base_agent_activate_from_paused():
    agent = BaseAgent()
    agent.status = "paused"
    assert agent.activate() is True
    assert agent.status == "active"

def test_base_agent_activate_when_active():
    agent = BaseAgent()
    agent.status = "active"
    assert agent.activate() is False
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

def test_base_agent_process_task_not_implemented():
    agent = BaseAgent()
    agent.activate()
    with pytest.raises(NotImplementedError, match="process_task method must be implemented by subclasses"):
        agent.process_task({"task_id": "1"})

def test_base_agent_process_task_not_active():
    agent = BaseAgent()
    with pytest.raises(RuntimeError, match="Agent not active"):
        agent.process_task({"task_id": "1"})

def test_base_agent_get_status():
    agent = BaseAgent()
    assert agent.get_status() == "initialized"
    agent.activate()
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

def test_base_agent_call_tool_placeholder():
    agent = BaseAgent()
    agent.tools["test_tool"] = MagicMock()
    result = agent._call_tool("test_tool", arg1="val1")
    assert result == "Result from test_tool"

def test_base_agent_call_tool_not_found():
    agent = BaseAgent()
    with pytest.raises(ValueError, match="Tool 'non_existent_tool' not available"):
        agent._call_tool("non_existent_tool")

def test_base_agent_interact_with_llm_placeholder():
    agent = BaseAgent()
    agent.llm_client = MagicMock()
    messages = [{'role': 'user', 'content': 'hello'}]
    result = agent._interact_with_llm(messages)
    assert result == "LLM response"

def test_base_agent_interact_with_llm_no_client():
    agent = BaseAgent()
    messages = [{'role': 'user', 'content': 'hello'}]
    with pytest.raises(RuntimeError, match="LLM client not available"):
        agent._interact_with_llm(messages)
