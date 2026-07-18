import pytest
import logging
from unittest.mock import MagicMock, patch
from core.runtime.observability_layer.metrics.metrics import MetricsManager, IMetricsManager

@pytest.fixture
def metrics_manager() -> IMetricsManager:
    return MetricsManager()

@pytest.mark.asyncio
async def test_record_metric(metrics_manager: IMetricsManager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.record_metric("test_metric", 123, {"key": "value"})
        assert "METRIC: test_metric, VALUE: 123, TAGS: {\'key\': \'value\'}" in caplog.text

@pytest.mark.asyncio
async def test_increment_counter(metrics_manager: IMetricsManager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.increment_counter("test_counter", {"type": "success"})
        assert "COUNTER INCREMENTED: test_counter, TAGS: {\'type\': \'success\'}" in caplog.text

@pytest.mark.asyncio
async def test_gauge(metrics_manager: IMetricsManager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.gauge("test_gauge", 45.6, {"unit": "percent"})
        assert "GAUGE: test_gauge, VALUE: 45.6, TAGS: {\'unit\': \'percent\'}" in caplog.text

@pytest.mark.asyncio
async def test_record_metric_no_tags(metrics_manager: IMetricsManager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.record_metric("test_metric_no_tags", 100)
        assert "METRIC: test_metric_no_tags, VALUE: 100, TAGS: None" in caplog.text

@pytest.mark.asyncio
async def test_increment_counter_no_tags(metrics_manager: IMetricsManager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.increment_counter("test_counter_no_tags")
        assert "COUNTER INCREMENTED: test_counter_no_tags, TAGS: None" in caplog.text

@pytest.mark.asyncio
async def test_gauge_no_tags(metrics_manager: IMetricsManager, caplog):
    with caplog.at_level(logging.INFO):
        metrics_manager.gauge("test_gauge_no_tags", 789)
        assert "GAUGE: test_gauge_no_tags, VALUE: 789, TAGS: None" in caplog.text
