import pytest
from src.core.autonomous_intelligence_layer.resource_optimizer.resource_optimizer import (
    ResourceOptimizer, ResourceOptimizerConfig, ResourceType, OptimizationStrategy,
    ResourceAllocation, ResourceConstraint, OptimizationResult
)


@pytest.fixture
def optimizer():
    return ResourceOptimizer()


@pytest.fixture
def sample_config():
    return ResourceOptimizerConfig(
        default_strategy=OptimizationStrategy.DYNAMIC_PROGRAMMING,
        enable_dynamic_reallocation=True,
        reallocation_interval_seconds=60,
        max_allocations=5000,
        efficiency_threshold=0.8
    )


def test_resource_optimizer_init(optimizer, sample_config):
    assert isinstance(optimizer.config, ResourceOptimizerConfig)
    assert not optimizer.allocations
    assert not optimizer.constraints
    assert not optimizer.optimization_history

    custom_optimizer = ResourceOptimizer(config=sample_config)
    assert custom_optimizer.config == sample_config


def test_add_constraint(optimizer):
    constraint = optimizer.add_constraint(
        "cpu_limit", ResourceType.CPU, 100.0, 10.0, 0.9
    )
    assert isinstance(constraint, ResourceConstraint)
    assert constraint.constraint_id == "cpu_limit"
    assert optimizer.constraints["cpu_limit"] == constraint


def test_allocate_resource_success(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    allocation = optimizer.allocate_resource(
        "alloc1", "agent1", ResourceType.CPU, 5.0
    )
    assert isinstance(allocation, ResourceAllocation)
    assert allocation.allocated_amount == 5.0
    assert optimizer.allocations["alloc1"] == allocation


def test_allocate_resource_no_constraint(optimizer):
    allocation = optimizer.allocate_resource(
        "alloc1", "agent1", ResourceType.CPU, 5.0
    )
    assert allocation is None


def test_allocate_resource_exceeds_per_agent_limit(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    allocation = optimizer.allocate_resource(
        "alloc1", "agent1", ResourceType.CPU, 15.0
    )
    assert allocation is None


def test_allocate_resource_exceeds_total_limit(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 10.0, 10.0)
    optimizer.allocate_resource("alloc1", "agent1", ResourceType.CPU, 7.0)
    allocation = optimizer.allocate_resource(
        "alloc2", "agent2", ResourceType.CPU, 5.0
    )
    assert allocation is None


def test_update_usage(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    allocation = optimizer.allocate_resource(
        "alloc1", "agent1", ResourceType.CPU, 5.0
    )
    assert allocation is not None
    updated = optimizer.update_usage("alloc1", 3.0)
    assert updated is True
    assert optimizer.allocations["alloc1"].used_amount == 3.0


def test_update_usage_not_found(optimizer):
    updated = optimizer.update_usage("non_existent_alloc", 3.0)
    assert updated is False


def test_optimize_allocation_greedy(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    optimizer.allocate_resource("alloc1", "agent1", ResourceType.CPU, 5.0)
    optimizer.allocations["alloc1"].used_amount = 4.0  # High efficiency
    optimizer.allocate_resource("alloc2", "agent2", ResourceType.CPU, 5.0)
    optimizer.allocations["alloc2"].used_amount = 1.0  # Low efficiency

    result = optimizer.optimize_allocation("opt1", ["agent1", "agent2"], OptimizationStrategy.GREEDY)
    assert isinstance(result, OptimizationResult)
    assert result.strategy == OptimizationStrategy.GREEDY
    assert len(result.allocations) == 2
    # Check if allocations were adjusted (e.g., alloc1 increased, alloc2 decreased)
    alloc1_optimized = next(a for a in result.allocations if a.agent_id == "agent1")
    alloc2_optimized = next(a for a in result.allocations if a.agent_id == "agent2")
    assert alloc1_optimized.allocated_amount > 5.0
    assert alloc2_optimized.allocated_amount < 5.0


def test_optimize_allocation_no_agents(optimizer):
    result = optimizer.optimize_allocation("opt1", [])
    assert result is None


def test_calculate_efficiency(optimizer):
    alloc1 = ResourceAllocation("id1", "agent1", ResourceType.CPU, 10.0, 8.0)
    alloc2 = ResourceAllocation("id2", "agent2", ResourceType.MEMORY, 20.0, 5.0)
    alloc3 = ResourceAllocation("id3", "agent3", ResourceType.API_CALLS, 0.0, 0.0)  # Should not cause division by zero

    efficiency = optimizer._calculate_efficiency([alloc1, alloc2, alloc3])
    # (0.8 + 0.25 + 0.0) / 3 = 0.35
    assert efficiency == pytest.approx((0.8 + 0.25 + 0.0) / 3)


def test_calculate_efficiency_empty_allocations(optimizer):
    efficiency = optimizer._calculate_efficiency([])
    assert efficiency == 0.0


def test_predict_resource_needs(optimizer):
    historical_data = {
        ResourceType.CPU: [10.0, 12.0, 11.0, 13.0, 14.0],
        ResourceType.MEMORY: [100.0, 110.0, 105.0]
    }
    predictions = optimizer.predict_resource_needs("agent1", historical_data)
    # CPU: (10+12+11+13+14)/5 * 1.2 = 12 * 1.2 = 14.4
    # MEMORY: (100+110+105)/3 * 1.2 = 105 * 1.2 = 126.0
    assert predictions[ResourceType.CPU] == pytest.approx(14.4)
    assert predictions[ResourceType.MEMORY] == pytest.approx(126.0)


def test_predict_resource_needs_empty_history(optimizer):
    historical_data = {
        ResourceType.CPU: [],
        ResourceType.MEMORY: [100.0]
    }
    predictions = optimizer.predict_resource_needs("agent1", historical_data)
    assert ResourceType.CPU not in predictions
    assert predictions[ResourceType.MEMORY] == pytest.approx(120.0)  # 100 * 1.2


def test_get_allocation(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    alloc = optimizer.allocate_resource("alloc1", "agent1", ResourceType.CPU, 5.0)
    retrieved_alloc = optimizer.get_allocation("alloc1")
    assert retrieved_alloc == alloc
    assert optimizer.get_allocation("non_existent") is None


def test_get_agent_allocations(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    optimizer.add_constraint("memory_limit", ResourceType.MEMORY, 200.0, 50.0)
    alloc1 = optimizer.allocate_resource("alloc1", "agent1", ResourceType.CPU, 5.0)
    optimizer.allocate_resource("alloc2", "agent2", ResourceType.CPU, 5.0)
    alloc3 = optimizer.allocate_resource("alloc3", "agent1", ResourceType.MEMORY, 20.0)

    agent1_allocs = optimizer.get_agent_allocations("agent1")
    assert len(agent1_allocs) == 2
    assert alloc1 in agent1_allocs
    assert alloc3 in agent1_allocs


def test_get_optimization_history(optimizer):
    optimizer.add_constraint("cpu_limit", ResourceType.CPU, 100.0, 10.0)
    optimizer.allocate_resource("alloc1", "agent1", ResourceType.CPU, 5.0)
    optimizer.optimize_allocation("opt1", ["agent1"], OptimizationStrategy.GREEDY)
    history = optimizer.get_optimization_history()
    assert len(history) == 1
    assert history[0].optimization_id == "opt1"
