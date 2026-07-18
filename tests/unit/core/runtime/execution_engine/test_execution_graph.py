import pytest
import logging
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.runtime.execution_engine.execution_graph import ExecutionGraph, IExecutionGraph
from core.runtime.execution_engine.executor import IExecutor
from core.runtime.execution_engine.dependency_resolver import IDependencyResolver

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.execution_engine.execution_graph").setLevel(logging.INFO)

@pytest.fixture
def mock_executor() -> AsyncMock:
    mock = AsyncMock(spec=IExecutor)
    async def _side_effect(task_id, task_function, **kwargs):
        return await task_function(**kwargs)
    mock.execute_task.side_effect = _side_effect
    return mock

@pytest.fixture
def mock_dependency_resolver() -> MagicMock:
    mock = MagicMock(spec=IDependencyResolver)
    mock.resolve.return_value = [] # Default to empty list
    return mock

@pytest.fixture
def execution_graph(mock_executor, mock_dependency_resolver) -> ExecutionGraph:
    return ExecutionGraph(
        executor=mock_executor,
        dependency_resolver=mock_dependency_resolver
    )

@pytest.mark.asyncio
async def test_execution_graph_empty_graph(execution_graph: ExecutionGraph, mock_dependency_resolver: MagicMock):
    graph_definition = {}
    mock_dependency_resolver.resolve.return_value = []
    results = await execution_graph.execute_graph(graph_definition)
    assert results == {}
    mock_dependency_resolver.resolve.assert_called_once_with({})

@pytest.mark.asyncio
async def test_execution_graph_simple_linear_flow(execution_graph: ExecutionGraph, mock_executor: AsyncMock, mock_dependency_resolver: MagicMock):
    async def task_a_func(): return "Result A"
    async def task_b_func(**kwargs): return f"Result B from {kwargs['dep_TaskA_result']}"

    graph_definition = {
        "TaskA": {"function": task_a_func, "dependencies": []},
        "TaskB": {"function": task_b_func, "dependencies": ["TaskA"]},
    }
    mock_dependency_resolver.resolve.return_value = ["TaskA", "TaskB"]

    results = await execution_graph.execute_graph(graph_definition)

    assert results["TaskA"] == "Result A"
    assert results["TaskB"] == "Result B from Result A"
    mock_executor.execute_task.assert_any_call("TaskA", task_a_func)
    mock_executor.execute_task.assert_any_call("TaskB", task_b_func, dep_TaskA_result="Result A")

@pytest.mark.asyncio
async def test_execution_graph_parallel_tasks(execution_graph: ExecutionGraph, mock_executor: AsyncMock, mock_dependency_resolver: MagicMock):
    async def task_p_func(): return "Result P"
    async def task_q_func(): return "Result Q"
    async def task_r_func(**kwargs): return f"Result R from {kwargs['dep_TaskP_result']} and {kwargs['dep_TaskQ_result']}"

    graph_definition = {
        "TaskP": {"function": task_p_func, "dependencies": []},
        "TaskQ": {"function": task_q_func, "dependencies": []},
        "TaskR": {"function": task_r_func, "dependencies": ["TaskP", "TaskQ"]},
    }
    mock_dependency_resolver.resolve.return_value = ["TaskP", "TaskQ", "TaskR"]

    results = await execution_graph.execute_graph(graph_definition)

    assert results["TaskP"] == "Result P"
    assert results["TaskQ"] == "Result Q"
    assert results["TaskR"] == "Result R from Result P and Result Q"
    mock_executor.execute_task.assert_any_call("TaskP", task_p_func)
    mock_executor.execute_task.assert_any_call("TaskQ", task_q_func)
    mock_executor.execute_task.assert_any_call("TaskR", task_r_func, dep_TaskP_result="Result P", dep_TaskQ_result="Result Q")

@pytest.mark.asyncio
async def test_execution_graph_task_failure(execution_graph: ExecutionGraph, mock_executor: AsyncMock, mock_dependency_resolver: MagicMock):
    async def task_fail_func(): raise ValueError("Task failed")

    graph_definition = {
        "TaskFail": {"function": task_fail_func, "dependencies": []},
    }
    mock_dependency_resolver.resolve.return_value = ["TaskFail"]
    mock_executor.execute_task.side_effect = ValueError("Task failed")

    with pytest.raises(ValueError, match="Task failed"):
        await execution_graph.execute_graph(graph_definition)
    mock_executor.execute_task.assert_called_once_with("TaskFail", task_fail_func, **{})

@pytest.mark.asyncio
async def test_execution_graph_circular_dependency(execution_graph: ExecutionGraph, mock_dependency_resolver: MagicMock):
    graph_definition = {
        "A": {"function": AsyncMock(), "dependencies": ["C"]},
        "B": {"function": AsyncMock(), "dependencies": ["A"]},
        "C": {"function": AsyncMock(), "dependencies": ["B"]},
    }
    mock_dependency_resolver.resolve.side_effect = ValueError("Circular dependency detected")

    with pytest.raises(ValueError, match="Circular dependency detected"):
        await execution_graph.execute_graph(graph_definition)
    mock_dependency_resolver.resolve.assert_called_once()

@pytest.mark.asyncio
async def test_execution_graph_with_kwargs(execution_graph: ExecutionGraph, mock_executor: AsyncMock, mock_dependency_resolver: MagicMock):
    async def task_with_kwargs_func(param1, param2): return f"Result: {param1}-{param2}"

    graph_definition = {
        "TaskWithKwargs": {"function": task_with_kwargs_func, "dependencies": [], "kwargs": {"param1": "val1", "param2": 123}},
    }
    mock_dependency_resolver.resolve.return_value = ["TaskWithKwargs"]

    results = await execution_graph.execute_graph(graph_definition)

    assert results["TaskWithKwargs"] == "Result: val1-123"
    mock_executor.execute_task.assert_called_once_with("TaskWithKwargs", task_with_kwargs_func, param1="val1", param2=123)

@pytest.mark.asyncio
async def test_execution_graph_dependency_result_injection_with_kwargs(execution_graph: ExecutionGraph, mock_executor: AsyncMock, mock_dependency_resolver: MagicMock):
    async def task_a_func(): return "A_data"
    async def task_b_func(**kwargs): return f"B_data from {kwargs["dep_TaskA_result"]} and {kwargs["fixed_param"]}"

    graph_definition = {
        "TaskA": {"function": task_a_func, "dependencies": []},
        "TaskB": {"function": task_b_func, "dependencies": ["TaskA"], "kwargs": {"fixed_param": "fixed"}},
    }
    mock_dependency_resolver.resolve.return_value = ["TaskA", "TaskB"]

    results = await execution_graph.execute_graph(graph_definition)

    assert results["TaskA"] == "A_data"
    assert results["TaskB"] == "B_data from A_data and fixed"
    mock_executor.execute_task.assert_any_call("TaskA", task_a_func)
    mock_executor.execute_task.assert_any_call("TaskB", task_b_func, dep_TaskA_result="A_data", fixed_param="fixed")

@pytest.mark.asyncio
async def test_execution_graph_undefined_dependency_in_graph_definition(execution_graph: ExecutionGraph, mock_dependency_resolver: MagicMock, caplog):
    async def task_a_func(): return "Result A"

    graph_definition = {
        "TaskA": {"function": task_a_func, "dependencies": []},
    }
    # Simulate resolver returning an extra dependency that is not in graph_definition
    mock_dependency_resolver.resolve.return_value = ["UndefinedDep", "TaskA"]

    results = await execution_graph.execute_graph(graph_definition)

    assert "Skipping task UndefinedDep as it is a dependency but not a defined task in the graph." in caplog.text
    assert "TaskA" in results
    assert "UndefinedDep" not in results


