import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.runtime.workflow_executor import WorkflowExecutor, IWorkflowExecutor
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@pytest.fixture
def workflow_executor() -> WorkflowExecutor:
    """Fixture لإنشاء مثيل WorkflowExecutor."""
    return WorkflowExecutor()


@pytest.mark.asyncio
async def test_workflow_executor_instance(workflow_executor: WorkflowExecutor):
    """اختبار أن WorkflowExecutor هو مثيل لـ IWorkflowExecutor."""
    assert isinstance(workflow_executor, IWorkflowExecutor)


@pytest.mark.asyncio
async def test_workflow_executor_execute_workflow_success(workflow_executor: WorkflowExecutor, caplog):
    """اختبار تنفيذ تدفق عمل بنجاح."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_1"
    workflow_definition = {"steps": ["step1", "step2"]}
    result = await workflow_executor.execute_workflow(workflow_id, workflow_definition)

    assert result["status"] == "COMPLETED"
    assert workflow_id in workflow_executor._active_workflows
    assert workflow_executor._active_workflows[workflow_id]["status"] == "RUNNING"
    assert "Workflow \'test_workflow_1\' started successfully." in caplog.text


@pytest.mark.asyncio
async def test_workflow_executor_pause_workflow_success(workflow_executor: WorkflowExecutor, caplog):
    """اختبار إيقاف تدفق عمل مؤقتاً بنجاح."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_2"
    workflow_definition = {"steps": ["step1", "step2"]}
    await workflow_executor.execute_workflow(workflow_id, workflow_definition)
    await workflow_executor.pause_workflow(workflow_id)

    assert workflow_executor._active_workflows[workflow_id]["status"] == "PAUSED"
    assert "Workflow \'test_workflow_2\' paused." in caplog.text


@pytest.mark.asyncio
async def test_workflow_executor_pause_workflow_not_found(workflow_executor: WorkflowExecutor, caplog):
    """اختبار محاولة إيقاف تدفق عمل غير موجود."""
    caplog.set_level(logging.WARNING)
    workflow_id = "non_existent_workflow"
    await workflow_executor.pause_workflow(workflow_id)

    assert "Workflow \'non_existent_workflow\' not found or not active. Cannot pause." in caplog.text


@pytest.mark.asyncio
async def test_workflow_executor_resume_workflow_success(workflow_executor: WorkflowExecutor, caplog):
    """اختبار استئناف تدفق عمل بنجاح."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_3"
    workflow_definition = {"steps": ["step1", "step2"]}
    await workflow_executor.execute_workflow(workflow_id, workflow_definition)
    await workflow_executor.pause_workflow(workflow_id)
    await workflow_executor.resume_workflow(workflow_id)

    assert workflow_executor._active_workflows[workflow_id]["status"] == "RUNNING"
    assert "Workflow \'test_workflow_3\' resumed." in caplog.text


@pytest.mark.asyncio
async def test_workflow_executor_resume_workflow_not_found(workflow_executor: WorkflowExecutor, caplog):
    """اختبار محاولة استئناف تدفق عمل غير موجود."""
    caplog.set_level(logging.WARNING)
    workflow_id = "non_existent_workflow_resume"
    await workflow_executor.resume_workflow(workflow_id)

    assert "Workflow \'non_existent_workflow_resume\' not found or not paused. Cannot resume." in caplog.text


@pytest.mark.asyncio
async def test_workflow_executor_terminate_workflow_success(workflow_executor: WorkflowExecutor, caplog):
    """اختبار إنهاء تدفق عمل بنجاح."""
    caplog.set_level(logging.INFO)
    workflow_id = "test_workflow_4"
    workflow_definition = {"steps": ["step1", "step2"]}
    await workflow_executor.execute_workflow(workflow_id, workflow_definition)
    await workflow_executor.terminate_workflow(workflow_id)

    assert workflow_id not in workflow_executor._active_workflows
    assert "Workflow \'test_workflow_4\' terminated." in caplog.text


@pytest.mark.asyncio
async def test_workflow_executor_terminate_workflow_not_found(workflow_executor: WorkflowExecutor, caplog):
    """اختبار محاولة إنهاء تدفق عمل غير موجود."""
    caplog.set_level(logging.WARNING)
    workflow_id = "non_existent_workflow_terminate"
    await workflow_executor.terminate_workflow(workflow_id)

    assert "Workflow \'non_existent_workflow_terminate\' not found or not active. Cannot terminate." in caplog.text
