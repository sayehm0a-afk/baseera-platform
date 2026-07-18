import pytest
import logging
import asyncio
from unittest.mock import AsyncMock

from core.runtime.execution_engine.executor import Executor, IExecutor

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.execution_engine.executor").setLevel(logging.INFO)

@pytest.fixture
def executor() -> Executor:
    return Executor()

@pytest.mark.asyncio
async def test_executor_execute_task_success(executor: Executor):
    async def mock_task_function(arg1: str, arg2: int) -> str:
        await asyncio.sleep(0.01)
        return f"Result: {arg1}-{arg2}"

    task_id = "test_success"
    result = await executor.execute_task(task_id, mock_task_function, arg1="hello", arg2=123)

    assert result == "Result: hello-123"

@pytest.mark.asyncio
async def test_executor_execute_task_failure(executor: Executor):
    async def mock_failing_task_function() -> None:
        await asyncio.sleep(0.01)
        raise ValueError("Simulated task failure")

    task_id = "test_failure"
    with pytest.raises(ValueError, match="Simulated task failure"):
        await executor.execute_task(task_id, mock_failing_task_function)

@pytest.mark.asyncio
async def test_executor_execute_task_no_kwargs(executor: Executor):
    async def mock_simple_task() -> str:
        await asyncio.sleep(0.01)
        return "Simple Result"

    task_id = "test_simple"
    result = await executor.execute_task(task_id, mock_simple_task)
    assert result == "Simple Result"

@pytest.mark.asyncio
async def test_executor_execute_task_async_mock_function(executor: Executor):
    mock_func = AsyncMock(return_value="Mocked Result")
    task_id = "test_async_mock"
    result = await executor.execute_task(task_id, mock_func, data="test")

    mock_func.assert_called_once_with(data="test")
    assert result == "Mocked Result"
