import pytest
from unittest.mock import AsyncMock, MagicMock
from core.runtime.workflow_state_machine import WorkflowStateMachine, IWorkflowStateMachine
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

@pytest.fixture
def workflow_state_machine() -> WorkflowStateMachine:
    """Fixture لإنشاء مثيل WorkflowStateMachine."""
    return WorkflowStateMachine()

@pytest.mark.asyncio
async def test_workflow_state_machine_instance(workflow_state_machine: WorkflowStateMachine):
    """اختبار أن WorkflowStateMachine هو مثيل لـ IWorkflowStateMachine."""
    assert isinstance(workflow_state_machine, IWorkflowStateMachine)

@pytest.mark.asyncio
async def test_workflow_state_machine_initial_state(workflow_state_machine: WorkflowStateMachine):
    """اختبار الحالة الأولية لتدفق عمل غير موجود."""
    workflow_id = "new_workflow"
    state = await workflow_state_machine.get_current_state(workflow_id)
    assert state == "UNKNOWN"

@pytest.mark.asyncio
async def test_workflow_state_machine_transition_state_success(workflow_state_machine: WorkflowStateMachine, caplog):
    """اختبار الانتقال بنجاح بين حالات تدفق العمل."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_1"
    initial_state = await workflow_state_machine.get_current_state(workflow_id)
    assert initial_state == "UNKNOWN"

    await workflow_state_machine.transition_state(workflow_id, "STARTED", {"user": "test"})
    current_state = await workflow_state_machine.get_current_state(workflow_id)
    assert current_state == "STARTED"
    assert "Workflow \"test_workflow_1\" transitioned from NONE to STARTED. Context: {\'user\': \'test\'}" in caplog.text

    await workflow_state_machine.transition_state(workflow_id, "PROCESSING", {"step": 1})
    current_state = await workflow_state_machine.get_current_state(workflow_id)
    assert current_state == "PROCESSING"
    assert "Workflow \"test_workflow_1\" transitioned from STARTED to PROCESSING. Context: {\'step\': 1}" in caplog.text

@pytest.mark.asyncio
async def test_workflow_state_machine_get_current_state(workflow_state_machine: WorkflowStateMachine):
    """اختبار الحصول على الحالة الحالية لتدفق عمل موجود."""
    workflow_id = "test_workflow_2"
    await workflow_state_machine.transition_state(workflow_id, "COMPLETED")
    state = await workflow_state_machine.get_current_state(workflow_id)
    assert state == "COMPLETED"
