"""
Unit tests for Resource Optimizer
"""

import pytest
from core.autonomous_intelligence_layer.resource_optimizer import (
    ResourceOptimizer,
    ResourceType,
    OptimizationStrategy,
    ResourceOptimizerConfig,
)


class TestResourceOptimizer:
    """Test cases for ResourceOptimizer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = ResourceOptimizer()

    def test_resource_optimizer_initialization(self):
        """Test that ResourceOptimizer initializes correctly."""
        assert self.optimizer is not None
        assert self.optimizer.config is not None
        assert isinstance(self.optimizer.config, ResourceOptimizerConfig)
        assert len(self.optimizer.allocations) == 0

    def test_resource_optimizer_with_custom_config(self):
        """Test ResourceOptimizer with custom config."""
        custom_config = ResourceOptimizerConfig(
            default_strategy=OptimizationStrategy.GENETIC_ALGORITHM,
            enable_dynamic_reallocation=False,
        )
        optimizer = ResourceOptimizer(config=custom_config)
        assert optimizer.config.default_strategy == OptimizationStrategy.GENETIC_ALGORITHM
        assert optimizer.config.enable_dynamic_reallocation is False

    def test_add_constraint(self):
        """Test adding a resource constraint."""
        constraint = self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        assert constraint is not None
        assert constraint.resource_type == ResourceType.CPU
        assert constraint.max_total == 1000.0

    def test_allocate_resource(self):
        """Test allocating a resource."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        allocation = self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )

        assert allocation is not None
        assert allocation.allocated_amount == 50.0
        assert allocation.agent_id == "agent_1"

    def test_allocate_resource_exceeds_max_per_agent(self):
        """Test allocation exceeding max per agent."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        allocation = self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=150.0,
        )

        assert allocation is None

    def test_allocate_resource_exceeds_total(self):
        """Test allocation exceeding total available."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=100.0,
            max_per_agent=100.0,
        )

        # First allocation
        alloc1 = self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=80.0,
        )
        assert alloc1 is not None

        # Second allocation exceeding total
        alloc2 = self.optimizer.allocate_resource(
            allocation_id="alloc_002",
            agent_id="agent_2",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )
        assert alloc2 is None

    def test_update_usage(self):
        """Test updating resource usage."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )

        result = self.optimizer.update_usage(allocation_id="alloc_001", used_amount=30.0)
        assert result is True

        allocation = self.optimizer.get_allocation("alloc_001")
        assert allocation.used_amount == 30.0

    def test_optimize_allocation_greedy(self):
        """Test optimization with greedy strategy."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        # Create allocations
        for i in range(3):
            self.optimizer.allocate_resource(
                allocation_id=f"alloc_{i:03d}",
                agent_id=f"agent_{i}",
                resource_type=ResourceType.CPU,
                amount=50.0,
            )

        # Update usage
        self.optimizer.update_usage("alloc_000", 40.0)
        self.optimizer.update_usage("alloc_001", 20.0)
        self.optimizer.update_usage("alloc_002", 45.0)

        # Optimize
        result = self.optimizer.optimize_allocation(
            optimization_id="opt_001",
            agent_ids=["agent_0", "agent_1", "agent_2"],
            strategy=OptimizationStrategy.GREEDY,
        )

        assert result is not None
        assert result.total_efficiency > 0

    def test_optimize_allocation_dynamic_programming(self):
        """Test optimization with dynamic programming strategy."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        for i in range(2):
            self.optimizer.allocate_resource(
                allocation_id=f"alloc_{i:03d}",
                agent_id=f"agent_{i}",
                resource_type=ResourceType.CPU,
                amount=50.0,
            )

        result = self.optimizer.optimize_allocation(
            optimization_id="opt_001",
            agent_ids=["agent_0", "agent_1"],
            strategy=OptimizationStrategy.DYNAMIC_PROGRAMMING,
        )

        assert result is not None

    def test_optimize_allocation_genetic_algorithm(self):
        """Test optimization with genetic algorithm strategy."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        for i in range(2):
            self.optimizer.allocate_resource(
                allocation_id=f"alloc_{i:03d}",
                agent_id=f"agent_{i}",
                resource_type=ResourceType.CPU,
                amount=50.0,
            )

        result = self.optimizer.optimize_allocation(
            optimization_id="opt_001",
            agent_ids=["agent_0", "agent_1"],
            strategy=OptimizationStrategy.GENETIC_ALGORITHM,
        )

        assert result is not None

    def test_optimize_allocation_no_agents(self):
        """Test optimization with no agents."""
        result = self.optimizer.optimize_allocation(
            optimization_id="opt_001",
            agent_ids=[],
        )

        assert result is None

    def test_predict_resource_needs(self):
        """Test predicting resource needs."""
        historical_data = {
            ResourceType.CPU: [10.0, 15.0, 12.0, 18.0, 20.0],
            ResourceType.MEMORY: [100.0, 120.0, 110.0, 130.0, 140.0],
        }

        predictions = self.optimizer.predict_resource_needs(
            agent_id="agent_1",
            historical_data=historical_data,
        )

        assert len(predictions) == 2
        assert predictions[ResourceType.CPU] > 0
        assert predictions[ResourceType.MEMORY] > 0

    def test_get_allocation(self):
        """Test retrieving an allocation."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )

        allocation = self.optimizer.get_allocation("alloc_001")
        assert allocation is not None
        assert allocation.allocated_amount == 50.0

    def test_get_nonexistent_allocation(self):
        """Test retrieving nonexistent allocation."""
        allocation = self.optimizer.get_allocation("nonexistent")
        assert allocation is None

    def test_get_agent_allocations(self):
        """Test retrieving agent allocations."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        for i in range(3):
            self.optimizer.allocate_resource(
                allocation_id=f"alloc_{i:03d}",
                agent_id="agent_1",
                resource_type=ResourceType.CPU,
                amount=20.0,
            )

        allocations = self.optimizer.get_agent_allocations("agent_1")
        assert len(allocations) == 3

    def test_optimization_history(self):
        """Test optimization history tracking."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )

        self.optimizer.optimize_allocation(
            optimization_id="opt_001",
            agent_ids=["agent_1"],
        )

        history = self.optimizer.get_optimization_history()
        assert len(history) == 1

    def test_multiple_resource_types(self):
        """Test handling multiple resource types."""
        self.optimizer.add_constraint(
            constraint_id="constraint_cpu",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        self.optimizer.add_constraint(
            constraint_id="constraint_memory",
            resource_type=ResourceType.MEMORY,
            max_total=10000.0,
            max_per_agent=1000.0,
        )

        cpu_alloc = self.optimizer.allocate_resource(
            allocation_id="alloc_cpu",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )

        memory_alloc = self.optimizer.allocate_resource(
            allocation_id="alloc_memory",
            agent_id="agent_1",
            resource_type=ResourceType.MEMORY,
            amount=500.0,
        )

        assert cpu_alloc is not None
        assert memory_alloc is not None

    def test_efficiency_calculation(self):
        """Test efficiency calculation."""
        self.optimizer.add_constraint(
            constraint_id="constraint_001",
            resource_type=ResourceType.CPU,
            max_total=1000.0,
            max_per_agent=100.0,
        )

        self.optimizer.allocate_resource(
            allocation_id="alloc_001",
            agent_id="agent_1",
            resource_type=ResourceType.CPU,
            amount=50.0,
        )

        self.optimizer.update_usage("alloc_001", 40.0)

        result = self.optimizer.optimize_allocation(
            optimization_id="opt_001",
            agent_ids=["agent_1"],
        )

        assert result.total_efficiency > 0.7  # 40/50 = 0.8
