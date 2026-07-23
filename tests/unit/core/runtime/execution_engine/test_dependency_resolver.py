import pytest
import logging
from src.core.runtime.execution_engine.dependency_resolver import DependencyResolver, IDependencyResolver


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.execution_engine.dependency_resolver").setLevel(logging.INFO)


@pytest.fixture
def dependency_resolver() -> DependencyResolver:
    return DependencyResolver()


@pytest.mark.asyncio
async def test_dependency_resolver_no_dependencies(dependency_resolver: DependencyResolver):
    tasks = {
        "A": [],
        "B": [],
        "C": []
    }
    resolved_order = dependency_resolver.resolve(tasks)
    assert len(resolved_order) == 3
    assert set(resolved_order) == set(["A", "B", "C"])


@pytest.mark.asyncio
async def test_dependency_resolver_simple_dependencies(dependency_resolver: DependencyResolver):
    tasks = {
        "A": [],
        "B": ["A"],
        "C": ["A", "B"]
    }
    resolved_order = dependency_resolver.resolve(tasks)
    assert resolved_order.index("A") < resolved_order.index("B")
    assert resolved_order.index("A") < resolved_order.index("C")
    assert resolved_order.index("B") < resolved_order.index("C")
    assert len(resolved_order) == 3
    assert set(resolved_order) == set(["A", "B", "C"])


@pytest.mark.asyncio
async def test_dependency_resolver_complex_dependencies(dependency_resolver: DependencyResolver):
    tasks = {
        "A": [],
        "B": ["A"],
        "C": ["A"],
        "D": ["B", "C"],
        "E": ["D"]
    }
    resolved_order = dependency_resolver.resolve(tasks)
    assert resolved_order.index("A") < resolved_order.index("B")
    assert resolved_order.index("A") < resolved_order.index("C")
    assert resolved_order.index("B") < resolved_order.index("D")
    assert resolved_order.index("C") < resolved_order.index("D")
    assert resolved_order.index("D") < resolved_order.index("E")
    assert len(resolved_order) == 5
    assert set(resolved_order) == set(["A", "B", "C", "D", "E"])


@pytest.mark.asyncio
async def test_dependency_resolver_circular_dependency(dependency_resolver: DependencyResolver):
    tasks = {
        "A": ["C"],
        "B": ["A"],
        "C": ["B"]
    }
    with pytest.raises(ValueError, match="Circular dependency detected in tasks."):
        dependency_resolver.resolve(tasks)


@pytest.mark.asyncio
async def test_dependency_resolver_empty_tasks(dependency_resolver: DependencyResolver):
    tasks = {}
    resolved_order = dependency_resolver.resolve(tasks)
    assert resolved_order == []


@pytest.mark.asyncio
async def test_dependency_resolver_self_dependency(dependency_resolver: DependencyResolver):
    tasks = {
        "A": ["A"]
    }
    with pytest.raises(ValueError, match="Circular dependency detected in tasks."):
        dependency_resolver.resolve(tasks)


@pytest.mark.asyncio
async def test_dependency_resolver_disconnected_graphs(dependency_resolver: DependencyResolver):
    tasks = {
        "X": [],
        "Y": [],
        "Z": ["Y"],
        "P": [],
        "Q": ["P"]
    }
    resolved_order = dependency_resolver.resolve(tasks)
    assert len(resolved_order) == 5
    assert set(resolved_order) == set(["X", "Y", "Z", "P", "Q"])
    assert resolved_order.index("Y") < resolved_order.index("Z")
    assert resolved_order.index("P") < resolved_order.index("Q")
