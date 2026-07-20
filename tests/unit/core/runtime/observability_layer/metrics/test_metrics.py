import pytest
import logging
from unittest.mock import patch
from src.core.runtime.observability_layer.metrics.metrics import MetricsManager, IMetricsManager
from typing import Any, Dict, Optional

@pytest.fixture
def metrics_manager():
    return MetricsManager()

def test_metrics_manager_init(metrics_manager):
    assert isinstance(metrics_manager, MetricsManager)
    assert isinstance(metrics_manager, IMetricsManager)

def test_record_metric(metrics_manager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.record_metric("test_metric", 123, {"tag1": "value1"})
        assert "METRIC: test_metric, VALUE: 123, TAGS: {\'tag1\': \'value1\'}" in caplog.text

def test_increment_counter(metrics_manager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.increment_counter("test_counter", {"tag2": "value2"})
        assert "COUNTER INCREMENTED: test_counter, TAGS: {\'tag2\': \'value2\'}" in caplog.text

def test_gauge(metrics_manager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.gauge("test_gauge", 45.6, {"tag3": "value3"})
        assert "GAUGE: test_gauge, VALUE: 45.6, TAGS: {\'tag3\': \'value3\'}" in caplog.text

def test_record_metric_no_tags(metrics_manager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.record_metric("test_metric_no_tags", 100)
        assert "METRIC: test_metric_no_tags, VALUE: 100, TAGS: None" in caplog.text

def test_increment_counter_no_tags(metrics_manager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.increment_counter("test_counter_no_tags")
        assert "COUNTER INCREMENTED: test_counter_no_tags, TAGS: None" in caplog.text

def test_gauge_no_tags(metrics_manager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.gauge("test_gauge_no_tags", 789)
        assert "GAUGE: test_gauge_no_tags, VALUE: 789, TAGS: None" in caplog.text

def test_abstract_methods_not_implemented():
    class ConcreteMetricsManager(IMetricsManager):
        def record_metric(self, name: str, value: Any, tags: Dict[str, str] = None):
            pass
        def increment_counter(self, name: str, tags: Dict[str, str] = None):
            pass
        def gauge(self, name: str, value: Any, tags: Dict[str, str] = None):
            pass

    manager = ConcreteMetricsManager()
    assert isinstance(manager, IMetricsManager)

    with pytest.raises(TypeError):
        # Cannot instantiate abstract class directly
        IMetricsManager()
