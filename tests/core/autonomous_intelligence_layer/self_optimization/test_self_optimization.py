"""
Unit tests for Self-Optimization
"""

import pytest
from core.autonomous_intelligence_layer.self_optimization import (
    SelfOptimization,
    OptimizationMetric,
    SelfOptimizationConfig,
)


class TestSelfOptimization:
    """Test cases for SelfOptimization class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = SelfOptimization()

    def test_self_optimization_initialization(self):
        """Test that SelfOptimization initializes correctly."""
        assert self.optimizer is not None
        assert self.optimizer.config is not None
        assert isinstance(self.optimizer.config, SelfOptimizationConfig)

    def test_self_optimization_with_custom_config(self):
        """Test SelfOptimization with custom config."""
        custom_config = SelfOptimizationConfig(
            enable_auto_tuning=False,
            min_improvement_threshold=2.0,
        )
        optimizer = SelfOptimization(config=custom_config)
        assert optimizer.config.enable_auto_tuning is False

    def test_record_metric(self):
        """Test recording a performance metric."""
        metric = self.optimizer.record_metric(
            metric_id="metric_001",
            metric_type=OptimizationMetric.LATENCY,
            value=100.0,
        )

        assert metric is not None
        assert metric.value == 100.0
        assert metric.metric_type == OptimizationMetric.LATENCY

    def test_set_parameter(self):
        """Test setting a system parameter."""
        result = self.optimizer.set_parameter("learning_rate", 0.01)
        assert result is True

    def test_get_parameter(self):
        """Test getting a system parameter."""
        self.optimizer.set_parameter("learning_rate", 0.01)
        value = self.optimizer.get_parameter("learning_rate")
        assert value == 0.01

    def test_get_nonexistent_parameter(self):
        """Test getting nonexistent parameter."""
        value = self.optimizer.get_parameter("nonexistent")
        assert value is None

    def test_optimize_parameters(self):
        """Test optimizing parameters."""
        # Record baseline metric
        self.optimizer.record_metric(
            metric_id="metric_001",
            metric_type=OptimizationMetric.LATENCY,
            value=100.0,
        )

        self.optimizer.set_parameter("batch_size", 32)

        def optimization_func():
            self.optimizer.set_parameter("batch_size", 64)
            self.optimizer.record_metric(
                metric_id="metric_002",
                metric_type=OptimizationMetric.LATENCY,
                value=80.0,
            )

        result = self.optimizer.optimize_parameters(
            optimization_id="opt_001",
            metric_type=OptimizationMetric.LATENCY,
            optimization_func=optimization_func,
        )

        assert result is not None
        assert result.improvement_percentage > 0

    def test_optimize_parameters_no_improvement(self):
        """Test optimization with no improvement."""
        self.optimizer.record_metric(
            metric_id="metric_001",
            metric_type=OptimizationMetric.LATENCY,
            value=100.0,
        )

        def optimization_func():
            self.optimizer.record_metric(
                metric_id="metric_002",
                metric_type=OptimizationMetric.LATENCY,
                value=99.5,
            )

        result = self.optimizer.optimize_parameters(
            optimization_id="opt_001",
            metric_type=OptimizationMetric.LATENCY,
            optimization_func=optimization_func,
        )

        # Should return None if improvement is below threshold
        assert result is None

    def test_get_metric(self):
        """Test retrieving a metric."""
        self.optimizer.record_metric(
            metric_id="metric_001",
            metric_type=OptimizationMetric.LATENCY,
            value=100.0,
        )

        metric = self.optimizer.get_metric("metric_001")
        assert metric is not None
        assert metric.value == 100.0

    def test_get_optimization(self):
        """Test retrieving an optimization result."""
        self.optimizer.record_metric(
            metric_id="metric_001",
            metric_type=OptimizationMetric.LATENCY,
            value=100.0,
        )

        self.optimizer.set_parameter("batch_size", 32)

        def optimization_func():
            self.optimizer.set_parameter("batch_size", 64)
            self.optimizer.record_metric(
                metric_id="metric_002",
                metric_type=OptimizationMetric.LATENCY,
                value=50.0,
            )

        self.optimizer.optimize_parameters(
            optimization_id="opt_001",
            metric_type=OptimizationMetric.LATENCY,
            optimization_func=optimization_func,
        )

        optimization = self.optimizer.get_optimization("opt_001")
        assert optimization is not None

    def test_get_metrics_by_type(self):
        """Test getting metrics by type."""
        for i in range(5):
            self.optimizer.record_metric(
                metric_id=f"metric_{i:03d}",
                metric_type=OptimizationMetric.LATENCY,
                value=100.0 + i * 10,
            )

        metrics = self.optimizer.get_metrics_by_type(OptimizationMetric.LATENCY)
        assert len(metrics) == 5

    def test_get_average_metric(self):
        """Test getting average metric value."""
        values = [100.0, 120.0, 110.0, 130.0, 140.0]

        for i, value in enumerate(values):
            self.optimizer.record_metric(
                metric_id=f"metric_{i:03d}",
                metric_type=OptimizationMetric.LATENCY,
                value=value,
            )

        average = self.optimizer.get_average_metric(OptimizationMetric.LATENCY)
        expected_average = sum(values) / len(values)
        assert average == expected_average

    def test_get_best_optimization(self):
        """Test getting best optimization result."""
        self.optimizer.record_metric(
            metric_id="metric_001",
            metric_type=OptimizationMetric.LATENCY,
            value=100.0,
        )

        # First optimization: 100 -> 80 (20% improvement)
        def opt_func_1():
            self.optimizer.record_metric(
                metric_id="metric_002",
                metric_type=OptimizationMetric.LATENCY,
                value=80.0,
            )

        self.optimizer.optimize_parameters(
            optimization_id="opt_001",
            metric_type=OptimizationMetric.LATENCY,
            optimization_func=opt_func_1,
        )

        # Second optimization: 80 -> 40 (50% improvement)
        def opt_func_2():
            self.optimizer.record_metric(
                metric_id="metric_003",
                metric_type=OptimizationMetric.LATENCY,
                value=40.0,
            )

        self.optimizer.optimize_parameters(
            optimization_id="opt_002",
            metric_type=OptimizationMetric.LATENCY,
            optimization_func=opt_func_2,
        )

        best = self.optimizer.get_best_optimization()
        assert best is not None
        assert best.optimization_id == "opt_002"

    def test_multiple_metric_types(self):
        """Test handling multiple metric types."""
        metric_types = [
            OptimizationMetric.LATENCY,
            OptimizationMetric.THROUGHPUT,
            OptimizationMetric.ACCURACY,
            OptimizationMetric.COST,
            OptimizationMetric.ERROR_RATE,
        ]

        for i, metric_type in enumerate(metric_types):
            self.optimizer.record_metric(
                metric_id=f"metric_{i:03d}",
                metric_type=metric_type,
                value=100.0 + i * 10,
            )

        assert len(self.optimizer.metrics) == len(metric_types)

    def test_improvement_calculation_lower_is_better(self):
        """Test improvement calculation for metrics where lower is better."""
        improvement = self.optimizer._calculate_improvement(
            old_value=100.0,
            new_value=80.0,
            metric_type=OptimizationMetric.LATENCY,
        )

        assert improvement == 20.0

    def test_improvement_calculation_higher_is_better(self):
        """Test improvement calculation for metrics where higher is better."""
        improvement = self.optimizer._calculate_improvement(
            old_value=80.0,
            new_value=100.0,
            metric_type=OptimizationMetric.ACCURACY,
        )

        assert improvement == 25.0

    def test_parameter_limit(self):
        """Test parameter limit enforcement."""
        config = SelfOptimizationConfig(max_parameters=5)
        optimizer = SelfOptimization(config=config)

        for i in range(5):
            result = optimizer.set_parameter(f"param_{i}", i)
            assert result is True

        # Should fail when limit reached
        result = optimizer.set_parameter("param_6", 6)
        assert result is False
