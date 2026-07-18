import pytest
from unittest.mock import AsyncMock, MagicMock
from core.runtime.workflow_context import WorkflowContext, IWorkflowContext
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

@pytest.fixture
def workflow_context() -> WorkflowContext:
    """Fixture لإنشاء مثيل WorkflowContext."""
    return WorkflowContext()

@pytest.mark.asyncio
async def test_workflow_context_instance(workflow_context: WorkflowContext):
    """اختبار أن WorkflowContext هو مثيل لـ IWorkflowContext."""
    assert isinstance(workflow_context, IWorkflowContext)

@pytest.mark.asyncio
async def test_workflow_context_initial_empty_context(workflow_context: WorkflowContext):
    """اختبار أن السياق الأولي لتدفق عمل غير موجود فارغ."""
    workflow_id = "new_workflow"
    context = await workflow_context.get_context(workflow_id)
    assert context == {}

@pytest.mark.asyncio
async def test_workflow_context_update_context_new_workflow(workflow_context: WorkflowContext, caplog):
    """اختبار تحديث سياق تدفق عمل جديد."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_1"
    updates = {"user_id": "123", "status": "STARTED"}
    await workflow_context.update_context(workflow_id, updates)

    context = await workflow_context.get_context(workflow_id)
    assert context == updates
    assert "Workflow \"test_workflow_1\" context updated with: {\'user_id\': \'123\', \'status\': \'STARTED\'}" in caplog.text

@pytest.mark.asyncio
async def test_workflow_context_update_context_existing_workflow(workflow_context: WorkflowContext, caplog):
    """اختبار تحديث سياق تدفق عمل موجود."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_2"
    initial_updates = {"user_id": "456", "step": 1}
    await workflow_context.update_context(workflow_id, initial_updates)

    additional_updates = {"step": 2, "result": "success"}
    await workflow_context.update_context(workflow_id, additional_updates)

    expected_context = {"user_id": "456", "step": 2, "result": "success"}
    context = await workflow_context.get_context(workflow_id)
    assert context == expected_context
    assert "Workflow \"test_workflow_2\" context updated with: {\'step\': 2, \'result\': \'success\'}" in caplog.text

@pytest.mark.asyncio
async def test_workflow_context_get_context_existing_workflow(workflow_context: WorkflowContext):
    """اختبار الحصول على سياق تدفق عمل موجود."""
    workflow_id = "test_workflow_3"
    updates = {"data": "some_data", "progress": 50}
    await workflow_context.update_context(workflow_id, updates)

    context = await workflow_context.get_context(workflow_id)
    assert context == updates
