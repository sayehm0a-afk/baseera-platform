import pytest
from unittest.mock import AsyncMock
from src.core.runtime.security_layer.permission_validation import PermissionValidation, IPermissionValidation

@pytest.fixture
def permission_validation() -> IPermissionValidation:
    return PermissionValidation()

@pytest.mark.asyncio
async def test_permission_validation_default_success(permission_validation: IPermissionValidation):
    agent_id = "test_agent"
    capability = "test_capability"
    context = {"resource": "test_resource"}

    is_allowed = await permission_validation.validate_permission(agent_id, capability, context)

    assert is_allowed is True

@pytest.mark.asyncio
async def test_permission_validation_with_different_inputs(permission_validation: IPermissionValidation):
    agent_id = "another_agent"
    capability = "another_capability"
    context = {"action": "read", "entity": "data"}

    is_allowed = await permission_validation.validate_permission(agent_id, capability, context)

    assert is_allowed is True

@pytest.mark.asyncio
async def test_permission_validation_empty_context(permission_validation: IPermissionValidation):
    agent_id = "agent_without_context"
    capability = "simple_action"
    context = {}

    is_allowed = await permission_validation.validate_permission(agent_id, capability, context)

    assert is_allowed is True
