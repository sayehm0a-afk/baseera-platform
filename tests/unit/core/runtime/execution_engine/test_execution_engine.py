import pytest
import logging
from unittest.mock import AsyncMock, MagicMock

from src.core.runtime.execution_engine.execution_engine import ExecutionEngine, IExecutionEngine
from src.core.runtime.execution_engine.executor import IExecutor
from src.core.runtime.execution_engine.dependency_resolver import IDependencyResolver
from src.core.runtime.execution_engine.execution_graph import IExecutionGraph


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.execution_engine.execution_engine").setLevel(logging.INFO)


@pytest.fixture
def mock_executor() -> AsyncMock:
    return AsyncMock(spec=IExecutor)


@pytest.fixture
def mock_dependency_resolver() -> MagicMock:
    return MagicMock(spec=IDependencyResolver)


@pytest.fixture
def mock_execution_graph() -> AsyncMock:
    return AsyncMock(spec=IExecutionGraph)


@pytest.fixture
def execution_engine(mock_executor, mock_dependency_resolver, mock_execution_graph) -> ExecutionEngine:
    return ExecutionEngine(
        executor=mock_executor,
        dependency_resolver=mock_dependency_resolver,
        execution_graph=mock_execution_graph
    )


@pytest.mark.asyncio
async def test_execution_engine_execute_workflow_success(execution_engine: ExecutionEngine, mock_execution_graph: AsyncMock):
    workflow_definition = {
        "Task1": {"function": AsyncMock(), "dependencies": []},
        "Task2": {"function": AsyncMock(), "dependencies": ["Task1"]},
    }
    expected_results = {"Task1": "Result1", "Task2": "Result2"}
    mock_execution_graph.execute_graph.return_value = expected_results

    results = await execution_engine.execute_workflow(workflow_definition)

    mock_execution_graph.execute_graph.assert_called_once_with(workflow_definition)
    assert results == expected_results


@pytest.mark.asyncio
async def test_execution_engine_execute_workflow_failure(execution_engine: ExecutionEngine, mock_execution_graph: AsyncMock):
    workflow_definition = {
        "Task1": {"function": AsyncMock(), "dependencies": []},
    }
    mock_execution_graph.execute_graph.side_effect = ValueError("Workflow execution failed")

    with pytest.raises(ValueError, match="Workflow execution failed"):
        await execution_engine.execute_workflow(workflow_definition)
    mock_execution_graph.execute_graph.assert_called_once_with(workflow_definition)


@pytest.mark.asyncio
async def test_execution_engine_initialization_with_defaults():
    # Test that if no mocks are provided, it initializes its own instances
    engine = ExecutionEngine()
    assert isinstance(engine._executor, IExecutor)
    assert isinstance(engine._dependency_resolver, IDependencyResolver)
    assert isinstance(engine._execution_graph, IExecutionGraph)


@pytest.mark.asyncio
async def test_execution_engine_initialization_with_provided_instances(mock_executor, mock_dependency_resolver, mock_execution_graph):
    engine = ExecutionEngine(
        executor=mock_executor,
        dependency_resolver=mock_dependency_resolver,
        execution_graph=mock_execution_graph
    )
    assert engine._executor == mock_executor
    assert engine._dependency_resolver == mock_dependency_resolver
    assert engine._execution_graph == mock_execution_graph
