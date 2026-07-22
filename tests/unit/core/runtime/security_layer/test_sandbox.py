import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from src.core.runtime.security_layer.sandbox import Sandbox, ISandbox

@pytest.fixture
def sandbox_instance() -> ISandbox:
    return Sandbox()

@pytest.mark.asyncio
async def test_create_sandbox(sandbox_instance: ISandbox):
    agent_id = "test_agent_1"
    config = {"memory": "2GB", "cpu": "2 cores"}
    
    sandbox_id = await sandbox_instance.create_sandbox(agent_id, config)
    
    assert isinstance(sandbox_id, str)
    assert sandbox_id.startswith(f"sandbox_{agent_id}")
    assert sandbox_id in sandbox_instance._sandboxes
    assert sandbox_instance._sandboxes[sandbox_id]["agent_id"] == agent_id
    assert sandbox_instance._sandboxes[sandbox_id]["config"] == config

@pytest.mark.asyncio
async def test_execute_in_sandbox_success(sandbox_instance: ISandbox):
    agent_id = "test_agent_2"
    config = {"disk": "20GB"}
    sandbox_id = await sandbox_instance.create_sandbox(agent_id, config)
    
    code_to_execute = "_result = 20 + 10"
    result = await sandbox_instance.execute_in_sandbox(sandbox_id, code_to_execute)
    
    assert result == {"simulated_result": "Code submitted for secure execution: _result = 20 + 10", "local_vars": None, "args": (), "kwargs": {}}

@pytest.mark.asyncio
async def test_execute_in_sandbox_with_args_kwargs(sandbox_instance: ISandbox):
    agent_id = "test_agent_3"
    config = {}
    sandbox_id = await sandbox_instance.create_sandbox(agent_id, config)
    
    code_to_execute = "_result = kwargs['b'] * args[0]"
    result = await sandbox_instance.execute_in_sandbox(sandbox_id, code_to_execute, 5, b=6)
    
    assert result == {"simulated_result": "Code submitted for secure execution: _result = kwargs['b'] * args[0]", "local_vars": None, "args": (5,), "kwargs": {'b': 6}}

@pytest.mark.asyncio
async def test_execute_in_non_existent_sandbox(sandbox_instance: ISandbox):
    non_existent_sandbox_id = "non_existent_sandbox"
    code_to_execute = "_result = 1 + 1"
    
    with pytest.raises(ValueError, match=f"Sandbox \'{non_existent_sandbox_id}\' not found."):
        await sandbox_instance.execute_in_sandbox(non_existent_sandbox_id, code_to_execute)

@pytest.mark.asyncio
async def test_execute_in_sandbox_failure(sandbox_instance: ISandbox):
    agent_id = "test_agent_4"
    config = {}
    sandbox_id = await sandbox_instance.create_sandbox(agent_id, config)
    
    code_to_execute = "raise RuntimeError(\'Sandbox Execution Error\')"
    
    with pytest.raises(ValueError, match="Simulated secure execution error"):
        await sandbox_instance.execute_in_sandbox(sandbox_id, code_to_execute, simulate_error=True)

@pytest.mark.asyncio
async def test_destroy_sandbox(sandbox_instance: ISandbox):
    agent_id = "test_agent_5"
    config = {}
    sandbox_id = await sandbox_instance.create_sandbox(agent_id, config)
    
    assert sandbox_id in sandbox_instance._sandboxes
    
    await sandbox_instance.destroy_sandbox(sandbox_id)
    
    assert sandbox_id not in sandbox_instance._sandboxes

@pytest.mark.asyncio
async def test_destroy_non_existent_sandbox(sandbox_instance: ISandbox, caplog):
    non_existent_sandbox_id = "non_existent_sandbox_to_destroy"
    
    await sandbox_instance.destroy_sandbox(non_existent_sandbox_id)
    
    with caplog.at_level(logging.WARNING):
        assert f"[Sandbox] Sandbox \'{non_existent_sandbox_id}\' not found for destruction." in caplog.text
