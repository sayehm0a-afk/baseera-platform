import pytest
from unittest.mock import MagicMock, patch
from core.runtime.observability_layer.metrics.metrics import MetricsManager, IMetricsManager

@pytest.fixture
def metrics_manager() -> IMetricsManager:
    return MetricsManager()

@pytest.mark.asyncio
async def test_record_metric(metrics_manager: IMetricsManager, capsys):
    metrics_manager.record_metric("test_metric", 123, {"key": "value"})
    captured = capsys.readouterr()
    assert "METRIC: test_metric, VALUE: 123, TAGS: {'key': 'value'}" in captured.out

@pytest.mark.asyncio
async def test_increment_counter(metrics_manager: IMetricsManager, capsys):
    metrics_manager.increment_counter("test_counter", {"type": "success"})
    captured = capsys.readouterr()
    assert "COUNTER INCREMENTED: test_counter, TAGS: {'type': 'success'}" in captured.out

@pytest.mark.asyncio
async def test_gauge(metrics_manager: IMetricsManager, capsys):
    metrics_manager.gauge("test_gauge", 45.6, {"unit": "percent"})
    captured = capsys.readouterr()
    assert "GAUGE: test_gauge, VALUE: 45.6, TAGS: {'unit': 'percent'}" in captured.out

@pytest.mark.asyncio
async def test_record_metric_no_tags(metrics_manager: IMetricsManager, capsys):
    metrics_manager.record_metric("test_metric_no_tags", 100)
    captured = capsys.readouterr()
    assert "METRIC: test_metric_no_tags, VALUE: 100, TAGS: None" in captured.out

@pytest.mark.asyncio
async def test_increment_counter_no_tags(metrics_manager: IMetricsManager, capsys):
    metrics_manager.increment_counter("test_counter_no_tags")
    captured = capsys.readouterr()
    assert "COUNTER INCREMENTED: test_counter_no_tags, TAGS: None" in captured.out

@pytest.mark.asyncio
async def test_gauge_no_tags(metrics_manager: IMetricsManager, capsys):
    metrics_manager.gauge("test_gauge_no_tags", 789)
    captured = capsys.readouterr()
    assert "GAUGE: test_gauge_no_tags, VALUE: 789, TAGS: None" in captured.out
