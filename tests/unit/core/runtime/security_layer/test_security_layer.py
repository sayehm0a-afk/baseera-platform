import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.runtime.security_layer.security_layer import SecurityLayer, ISecurityLayer
from src.core.runtime.security_layer.permission_validation import IPermissionValidation
from src.core.runtime.security_layer.agent_isolation import IAgentIsolation
from src.core.runtime.security_layer.sandbox import ISandbox


@pytest.fixture
def mock_permission_validation() -> AsyncMock:
    return AsyncMock(spec=IPermissionValidation)


@pytest.fixture
def mock_agent_isolation() -> AsyncMock:
    return AsyncMock(spec=IAgentIsolation)


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    return AsyncMock(spec=ISandbox)


@pytest.fixture
def security_layer(
    mock_permission_validation: AsyncMock,
    mock_agent_isolation: AsyncMock,
    mock_sandbox: AsyncMock
) -> ISecurityLayer:
    return SecurityLayer(
        permission_validation=mock_permission_validation,
        agent_isolation=mock_agent_isolation,
        sandbox=mock_sandbox
    )


@pytest.mark.asyncio
async def test_validate_and_execute_success_no_sandbox(
    security_layer: ISecurityLayer,
    mock_permission_validation: AsyncMock,
    mock_sandbox: AsyncMock
):
    agent_id = "test_agent"
    capability = "read_data"
    mock_func = AsyncMock(return_value="data_read")
    context = {"user": "admin"}

    mock_permission_validation.validate_permission.return_value = True

    result = await security_layer.validate_and_execute(
        agent_id, capability, mock_func, context=context, use_sandbox=False
    )

    assert result == "data_read"
    mock_permission_validation.validate_permission.assert_called_once_with(agent_id, capability, context)
    mock_func.assert_called_once_with()
    mock_sandbox.create_sandbox.assert_not_called()
    mock_sandbox.execute_in_sandbox.assert_not_called()
    mock_sandbox.destroy_sandbox.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_execute_permission_denied(
    security_layer: ISecurityLayer,
    mock_permission_validation: AsyncMock
):
    agent_id = "unauthorized_agent"
    capability = "write_data"
    mock_func = AsyncMock()
    context = {"user": "guest"}

    mock_permission_validation.validate_permission.return_value = False

    with pytest.raises(PermissionError, match=f"Agent '{agent_id}' is not authorized to perform capability '{capability}'"):
        await security_layer.validate_and_execute(
            agent_id, capability, mock_func, context=context, use_sandbox=False
        )

    mock_permission_validation.validate_permission.assert_called_once_with(agent_id, capability, context)
    mock_func.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_execute_with_sandbox_success(
    security_layer: ISecurityLayer,
    mock_permission_validation: AsyncMock,
    mock_sandbox: AsyncMock
):
    agent_id = "sandbox_agent"
    capability = "execute_script"
    mock_func = AsyncMock(return_value="script_executed")
    sandbox_config = {"timeout": 60}

    mock_permission_validation.validate_permission.return_value = True
    mock_sandbox.create_sandbox.return_value = "sandbox_123"
    mock_sandbox.execute_in_sandbox.return_value = "script_executed"

    result = await security_layer.validate_and_execute(
        agent_id, capability, mock_func, use_sandbox=True, sandbox_config=sandbox_config
    )

    assert result == "script_executed"
    mock_permission_validation.validate_permission.assert_called_once_with(agent_id, capability, {})
    mock_sandbox.create_sandbox.assert_called_once_with(agent_id, sandbox_config)
    mock_sandbox.execute_in_sandbox.assert_called_once()
    mock_sandbox.destroy_sandbox.assert_called_once_with("sandbox_123")
    mock_func.assert_not_called() # func should not be called directly when using sandbox


@pytest.mark.asyncio
async def test_validate_and_execute_with_sandbox_failure(
    security_layer: ISecurityLayer,
    mock_permission_validation: AsyncMock,
    mock_sandbox: AsyncMock
):
    agent_id = "failing_sandbox_agent"
    capability = "risky_operation"
    mock_func = AsyncMock(side_effect=ValueError("Sandbox error"))

    mock_permission_validation.validate_permission.return_value = True
    mock_sandbox.create_sandbox.return_value = "sandbox_456"
    mock_sandbox.execute_in_sandbox.side_effect = ValueError("Sandbox execution failed")

    with pytest.raises(ValueError, match="Sandbox execution failed"):
        await security_layer.validate_and_execute(
            agent_id, capability, mock_func, use_sandbox=True
        )

    mock_permission_validation.validate_permission.assert_called_once_with(agent_id, capability, {})
    mock_sandbox.create_sandbox.assert_called_once_with(agent_id, {})
    mock_sandbox.execute_in_sandbox.assert_called_once()
    mock_sandbox.destroy_sandbox.assert_called_once_with("sandbox_456")
    mock_func.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_execute_with_args_kwargs_no_sandbox(
    security_layer: ISecurityLayer,
    mock_permission_validation: AsyncMock,
    mock_sandbox: AsyncMock
):
    agent_id = "arg_kwarg_agent"
    capability = "process_data"
    mock_func = AsyncMock(return_value="processed_data")

    mock_permission_validation.validate_permission.return_value = True

    result = await security_layer.validate_and_execute(
        agent_id, capability, mock_func, "arg1", kwarg1="value1", context={}
    )

    assert result == "processed_data"
    mock_permission_validation.validate_permission.assert_called_once_with(agent_id, capability, {})
    mock_func.assert_called_once_with("arg1", kwarg1="value1")
    mock_sandbox.create_sandbox.assert_not_called()
    mock_sandbox.execute_in_sandbox.assert_not_called()
    mock_sandbox.destroy_sandbox.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_execute_with_args_kwargs_with_sandbox(
    security_layer: ISecurityLayer,
    mock_permission_validation: AsyncMock,
    mock_sandbox: AsyncMock
):
    agent_id = "sandbox_arg_kwarg_agent"
    capability = "complex_calculation"
    mock_func = AsyncMock(return_value=100)
    sandbox_config = {"memory": "4GB"}

    mock_permission_validation.validate_permission.return_value = True
    mock_sandbox.create_sandbox.return_value = "sandbox_789"
    mock_sandbox.execute_in_sandbox.return_value = 100

    result = await security_layer.validate_and_execute(
        agent_id, capability, mock_func, "input_data", factor=10, use_sandbox=True, sandbox_config=sandbox_config
    )

    assert result == 100
    mock_permission_validation.validate_permission.assert_called_once_with(agent_id, capability, {})
    mock_sandbox.create_sandbox.assert_called_once_with(agent_id, sandbox_config)
    # Verify execute_in_sandbox was called with the correct code and local_vars
    mock_sandbox.execute_in_sandbox.assert_called_once_with(
        "sandbox_789",
        "_result = local_vars['func'](*local_vars['args'], **local_vars['kwargs'])",
        local_vars={'func': mock_func, 'args': ('input_data',), 'kwargs': {'factor': 10}}
    )
    mock_sandbox.destroy_sandbox.assert_called_once_with("sandbox_789")
    mock_func.assert_not_called()


@pytest.mark.asyncio
async def test_security_layer_initialization_with_defaults():
    layer = SecurityLayer()
    assert isinstance(layer._permission_validation, IPermissionValidation)
    assert isinstance(layer._agent_isolation, IAgentIsolation)
    assert isinstance(layer._sandbox, ISandbox)


@pytest.mark.asyncio
async def test_security_layer_initialization_with_provided_instances(
    mock_permission_validation,
    mock_agent_isolation,
    mock_sandbox
):
    layer = SecurityLayer(
        permission_validation=mock_permission_validation,
        agent_isolation=mock_agent_isolation,
        sandbox=mock_sandbox
    )
    assert layer._permission_validation == mock_permission_validation
    assert layer._agent_isolation == mock_agent_isolation
    assert layer._sandbox == mock_sandbox
