import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from src.core.runtime.security_layer.agent_isolation import AgentIsolation, IAgentIsolation

@pytest.fixture
def agent_isolation() -> IAgentIsolation:
    return AgentIsolation()

@pytest.mark.asyncio
async def test_create_isolated_environment(agent_isolation: IAgentIsolation):
    agent_id = "test_agent_1"
    config = {"memory": "1GB", "cpu": "1 core"}
    
    environment_id = await agent_isolation.create_isolated_environment(agent_id, config)
    
    assert isinstance(environment_id, str)
    assert environment_id.startswith(f"isolated_env_{agent_id}")
    assert environment_id in agent_isolation._environments
    assert agent_isolation._environments[environment_id]["agent_id"] == agent_id
    assert agent_isolation._environments[environment_id]["config"] == config

@pytest.mark.asyncio
async def test_execute_in_isolated_environment_success(agent_isolation: IAgentIsolation):
    agent_id = "test_agent_2"
    config = {"disk": "10GB"}
    environment_id = await agent_isolation.create_isolated_environment(agent_id, config)
    
    code_to_execute = "_result = 10 + 5"
    result = await agent_isolation.execute_in_isolated_environment(environment_id, code_to_execute)
    
    assert result == {"simulated_result": "Code submitted for secure execution: _result = 10 + 5", "args": (), "kwargs": {}}

@pytest.mark.asyncio
async def test_execute_in_isolated_environment_with_args_kwargs(agent_isolation: IAgentIsolation):
    agent_id = "test_agent_3"
    config = {}
    environment_id = await agent_isolation.create_isolated_environment(agent_id, config)
    
    code_to_execute = "_result = kwargs['a'] + args[0]"
    result = await agent_isolation.execute_in_isolated_environment(environment_id, code_to_execute, 20, a=10)

    
    assert result == {"simulated_result": "Code submitted for secure execution: _result = kwargs['a'] + args[0]", "args": (20,), "kwargs": {'a': 10}}

@pytest.mark.asyncio
async def test_execute_in_non_existent_environment(agent_isolation: IAgentIsolation):
    non_existent_env_id = "non_existent_env"
    code_to_execute = "_result = 1 + 1"
    
    with pytest.raises(ValueError, match=f"Environment '{non_existent_env_id}' not found."):
        await agent_isolation.execute_in_isolated_environment(non_existent_env_id, code_to_execute)

@pytest.mark.asyncio
async def test_execute_in_isolated_environment_failure(agent_isolation: IAgentIsolation):
    agent_id = "test_agent_4"
    config = {}
    environment_id = await agent_isolation.create_isolated_environment(agent_id, config)
    
    code_to_execute = "raise ValueError('Execution Error')"
    
    with pytest.raises(ValueError, match="Simulated secure execution error"):
        await agent_isolation.execute_in_isolated_environment(environment_id, code_to_execute, simulate_error=True)

@pytest.mark.asyncio
async def test_destroy_isolated_environment(agent_isolation: IAgentIsolation):
    agent_id = "test_agent_5"
    config = {}
    environment_id = await agent_isolation.create_isolated_environment(agent_id, config)
    
    assert environment_id in agent_isolation._environments
    
    await agent_isolation.destroy_isolated_environment(environment_id)
    
    assert environment_id not in agent_isolation._environments

@pytest.mark.asyncio
async def test_destroy_non_existent_environment(agent_isolation: IAgentIsolation, caplog):
    non_existent_env_id = "non_existent_env_to_destroy"
    
    await agent_isolation.destroy_isolated_environment(non_existent_env_id)
    
    with caplog.at_level(logging.WARNING):
        assert f"[AgentIsolation] Environment \'{non_existent_env_id}\' not found for destruction." in caplog.text
