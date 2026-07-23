
import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock
from src.core.autonomous_intelligence_layer.self_optimization.self_optimization import (
    SelfOptimization, SelfOptimizationConfig, PerformanceMetric, OptimizationResult, OptimizationMetric
)


@pytest.fixture
def self_optimization():
    return SelfOptimization()


@pytest.fixture
def sample_config():
    return SelfOptimizationConfig(
        enable_auto_tuning=True,
        optimization_interval_seconds=60,
        min_improvement_threshold=2.0, # Changed to 2.0 to make 1% improvement not meet the threshold
        max_parameters=5
    )


def test_self_optimization_init(self_optimization, sample_config):
    assert isinstance(self_optimization.config, SelfOptimizationConfig)
    assert not self_optimization.metrics
    assert not self_optimization.optimizations
    assert not self_optimization.parameters
    assert not self_optimization.baseline_metrics

    custom_optimizer = SelfOptimization(config=sample_config)
    assert custom_optimizer.config == sample_config


def test_record_metric_success(self_optimization):
    metric = self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    assert isinstance(metric, PerformanceMetric)
    assert metric.metric_id == "lat1"
    assert self_optimization.metrics["lat1"] == metric
    assert self_optimization.baseline_metrics[OptimizationMetric.LATENCY] == 100.0


def test_set_parameter_success(self_optimization):
    assert self_optimization.set_parameter("thread_count", 4)
    assert self_optimization.parameters["thread_count"] == 4


def test_set_parameter_limit_reached(self_optimization, sample_config):
    custom_optimizer = SelfOptimization(config=sample_config)
    for i in range(sample_config.max_parameters):
        custom_optimizer.set_parameter(f"param{i}", i)

    assert not custom_optimizer.set_parameter("param_exceed", 10)


def test_get_parameter(self_optimization):
    self_optimization.set_parameter("timeout", 30)
    assert self_optimization.get_parameter("timeout") == 30
    assert self_optimization.get_parameter("non_existent") is None


def test_optimize_parameters_success(self_optimization):
    self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    self_optimization.set_parameter("buffer_size", 1024)

    def mock_optimization_func():
        self_optimization.set_parameter("buffer_size", 2048)
        self_optimization.record_metric("lat2", OptimizationMetric.LATENCY, 90.0)

    result = self_optimization.optimize_parameters(
        "opt1", OptimizationMetric.LATENCY, mock_optimization_func
    )
    assert isinstance(result, OptimizationResult)
    assert result.optimization_id == "opt1"
    assert result.metric_type == OptimizationMetric.LATENCY
    assert result.baseline_value == 100.0
    assert result.optimized_value == 90.0
    assert result.improvement_percentage == pytest.approx(10.0)
    assert result.parameters_changed == {"buffer_size": (1024, 2048)}


def test_optimize_parameters_no_improvement(sample_config):
    self_optimization = SelfOptimization(config=sample_config)
    self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    self_optimization.set_parameter("buffer_size", 1024)

    def mock_optimization_func():
        self_optimization.set_parameter("buffer_size", 2048)
        self_optimization.record_metric("lat2", OptimizationMetric.LATENCY, 99.0) # Only 1% improvement

    result = self_optimization.optimize_parameters(
        "opt1", OptimizationMetric.LATENCY, mock_optimization_func
    )
    assert result is None


def test_optimize_parameters_no_metrics(self_optimization):
    def mock_optimization_func():
        pass

    result = self_optimization.optimize_parameters(
        "opt1", OptimizationMetric.LATENCY, mock_optimization_func
    )
    assert result is None


def test_optimize_parameters_exception_rollback(self_optimization):
    self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    self_optimization.set_parameter("buffer_size", 1024)

    def mock_optimization_func_with_error():
        self_optimization.set_parameter("buffer_size", 2048)
        raise ValueError("Simulated error")

    old_parameters = dict(self_optimization.parameters)
    result = self_optimization.optimize_parameters(
        "opt1", OptimizationMetric.LATENCY, mock_optimization_func_with_error
    )
    assert result is None
    assert self_optimization.parameters == old_parameters # Parameters should be rolled back


def test_calculate_improvement_latency_lower_is_better(self_optimization):
    improvement = self_optimization._calculate_improvement(100.0, 90.0, OptimizationMetric.LATENCY)
    assert improvement == pytest.approx(10.0)


def test_calculate_improvement_throughput_higher_is_better(self_optimization):
    improvement = self_optimization._calculate_improvement(100.0, 110.0, OptimizationMetric.THROUGHPUT)
    assert improvement == pytest.approx(10.0)


def test_calculate_improvement_no_change(self_optimization):
    improvement = self_optimization._calculate_improvement(100.0, 100.0, OptimizationMetric.LATENCY)
    assert improvement == pytest.approx(0.0)


def test_calculate_improvement_zero_old_value(self_optimization):
    improvement = self_optimization._calculate_improvement(0.0, 10.0, OptimizationMetric.LATENCY)
    assert improvement == pytest.approx(0.0)


def test_get_metric(self_optimization):
    metric = self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    assert self_optimization.get_metric("lat1") == metric
    assert self_optimization.get_metric("non_existent") is None


def test_get_optimization(self_optimization):
    self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)

    def mock_optimization_func():
        self_optimization.record_metric("lat2", OptimizationMetric.LATENCY, 90.0)
    opt_result = self_optimization.optimize_parameters("opt1", OptimizationMetric.LATENCY, mock_optimization_func)
    assert self_optimization.get_optimization("opt1") == opt_result
    assert self_optimization.get_optimization("non_existent") is None


def test_get_metrics_by_type(self_optimization):
    metric1 = self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    metric2 = self_optimization.record_metric("lat2", OptimizationMetric.LATENCY, 90.0)
    metric3 = self_optimization.record_metric("thr1", OptimizationMetric.THROUGHPUT, 500.0)

    latency_metrics = self_optimization.get_metrics_by_type(OptimizationMetric.LATENCY)
    assert len(latency_metrics) == 2
    assert metric1 in latency_metrics
    assert metric2 in latency_metrics


def test_get_average_metric(self_optimization):
    self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    self_optimization.record_metric("lat2", OptimizationMetric.LATENCY, 90.0)
    assert self_optimization.get_average_metric(OptimizationMetric.LATENCY) == pytest.approx(95.0)
    assert self_optimization.get_average_metric(OptimizationMetric.THROUGHPUT) == pytest.approx(0.0)


def test_get_best_optimization(self_optimization):
    self_optimization.record_metric("lat1", OptimizationMetric.LATENCY, 100.0)
    self_optimization.record_metric("lat2", OptimizationMetric.LATENCY, 80.0)
    self_optimization.record_metric("lat3", OptimizationMetric.LATENCY, 70.0)

    def opt_func1():
        self_optimization.record_metric("lat_opt1", OptimizationMetric.LATENCY, 90.0)

    def opt_func2():
        self_optimization.record_metric("lat_opt2", OptimizationMetric.LATENCY, 75.0)

    opt_result1 = self_optimization.optimize_parameters("opt1", OptimizationMetric.LATENCY, opt_func1)
    opt_result2 = self_optimization.optimize_parameters("opt2", OptimizationMetric.LATENCY, opt_func2)

    best_opt = self_optimization.get_best_optimization()
    assert best_opt == opt_result2


def test_get_best_optimization_empty(self_optimization):
    best_opt = self_optimization.get_best_optimization()
    assert best_opt is None
