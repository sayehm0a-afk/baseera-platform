import pytest
from unittest.mock import MagicMock
from src.core.runtime.observability_layer.observability_layer import ObservabilityLayer
from src.core.runtime.observability_layer.metrics.metrics import IMetricsManager, MetricsManager
from src.core.runtime.observability_layer.tracing.tracing import ITracer, Tracer
from src.core.runtime.observability_layer.health_checks.health_checks import IHealthCheckManager, HealthCheckManager


@pytest.fixture
def observability_layer():
    return ObservabilityLayer()

def test_observability_layer_init(observability_layer):
    assert isinstance(observability_layer.metrics, MetricsManager)
    assert isinstance(observability_layer.tracer, Tracer)
    assert isinstance(observability_layer.health_checks, HealthCheckManager)

def test_metrics_property(observability_layer):
    metrics_manager = observability_layer.metrics
    assert isinstance(metrics_manager, IMetricsManager)
    assert isinstance(metrics_manager, MetricsManager)

def test_tracer_property(observability_layer):
    tracer = observability_layer.tracer
    assert isinstance(tracer, ITracer)
    assert isinstance(tracer, Tracer)

def test_health_checks_property(observability_layer):
    health_checks_manager = observability_layer.health_checks
    assert isinstance(health_checks_manager, IHealthCheckManager)
    assert isinstance(health_checks_manager, HealthCheckManager)
