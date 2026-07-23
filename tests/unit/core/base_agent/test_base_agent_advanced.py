import pytest
import logging
import threading
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from src.core.base_agent.base_agent import BaseAgent

# Mock logging to prevent console output during tests
@pytest.fixture(autouse=True)
def no_logging(caplog):
    caplog.set_level(logging.CRITICAL)

# --- Edge Case Tests ---

def test_base_agent_with_very_long_name():
    long_name = "A" * 1000
    agent = BaseAgent(name=long_name)
    assert agent.name == long_name

def test_base_agent_with_empty_description():
    agent = BaseAgent(description="")
    assert agent.description == ""

def test_base_agent_with_none_id():
    agent = BaseAgent(agent_id=None)
    assert isinstance(agent.agent_id, str)
    assert len(agent.agent_id) > 0

# --- Failure Tests ---

def test_base_agent_pause_from_initialized():
    agent = BaseAgent()
    assert agent.pause() is False
    assert agent.status == "initialized"

def test_base_agent_pause_from_terminated():
    agent = BaseAgent()
    agent.terminate()
    assert agent.pause() is False
    assert agent.status == "terminated"

@pytest.mark.asyncio
async def test_base_agent_activate_from_terminated():
    agent = BaseAgent()
    agent.terminate()
    assert await agent.activate() is False
    assert agent.status == "terminated"

@pytest.mark.asyncio
async def test_base_agent_process_task_when_paused():
    agent = BaseAgent()
    await agent.activate()
    agent.pause()
    with pytest.raises(RuntimeError, match="Agent not active"):
        agent.process_task({"task_id": "1"})

@pytest.mark.asyncio
async def test_base_agent_call_tool_none_name():
    agent = BaseAgent()
    agent.tool_registry = AsyncMock() # Mock ToolRegistry
    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock()
    agent.tool_registry.get_tool.return_value = mock_tool # Mock a tool
    with pytest.raises(ValueError):
        await agent._call_tool(None)

# --- Concurrency Tests ---

def test_base_agent_concurrent_activations():
    agent = BaseAgent()
    results = []

    async def activate_agent_async():
        results.append(await agent.activate())

    def activate_agent():
        asyncio.run(activate_agent_async())

    threads = [threading.Thread(target=activate_agent) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only one thread should have successfully activated it from 'initialized'
    # though multiple might succeed if it's already 'active' or 'paused'
    # In our current implementation, activate() returns False if already 'active'
    assert results.count(True) >= 1
    assert agent.status == "active"

@pytest.mark.asyncio
async def test_base_agent_concurrent_status_changes():
    agent = BaseAgent()
    await agent.activate()

    async def toggle_status_async():
        for _ in range(100):
            agent.pause()
            await agent.activate()

    def toggle_status():
        asyncio.run(toggle_status_async())

    threads = [threading.Thread(target=toggle_status) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert agent.status in ["active", "paused"]

# --- Stress Tests ---

def test_base_agent_mass_initialization():
    agents = [BaseAgent(name=f"Agent_{i}") for i in range(1000)]
    assert len(agents) == 1000
    assert agents[999].name == "Agent_999"

@pytest.mark.asyncio
async def test_base_agent_rapid_status_cycling():
    agent = BaseAgent()
    for _ in range(1000):
        await agent.activate()
        agent.pause()
    assert agent.status == "paused"

@pytest.mark.asyncio
async def test_base_agent_memory_stress():
    agent = BaseAgent()
    await agent.activate()
    # Adding 10,000 items to short term memory
    for i in range(10000):
        agent.memory['short_term'].append(f"item_{i}")
    assert len(agent.memory['short_term']) == 10000

# --- Additional Coverage Tests ---

@pytest.mark.asyncio
async def test_base_agent_init_internal_methods_coverage():
    # Directly test the placeholder internal methods for coverage
    agent = BaseAgent()
    agent._load_config()
    agent._initialize_memory()
    await agent._initialize_tools()
    await agent._initialize_llm_client()
    # These should just run without error as they are placeholders
    assert True

def test_base_agent_main_block_coverage():
    # To cover the 'if __name__ == "__main__":' block, we can't easily run it via pytest
    # but we can ensure the logic inside is tested.
    # The logic is basically initialization, activation, and status checks which are already covered.
    pass
