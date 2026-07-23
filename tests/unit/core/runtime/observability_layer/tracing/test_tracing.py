import pytest
from src.core.runtime.observability_layer.tracing.tracing import Tracer, Span, get_tracer, ITracer


@pytest.fixture
def tracer() -> ITracer:
    # Reset the global tracer for each test to ensure isolation
    global _global_tracer
    _global_tracer = Tracer()
    return _global_tracer


@pytest.mark.asyncio
async def test_start_span(tracer: ITracer):
    span = tracer.start_span("test_span")
    assert isinstance(span, Span)
    assert span.name == "test_span"
    assert tracer.current_span() == span
    span.end()
    assert tracer.current_span() is None


@pytest.mark.asyncio
async def test_span_attributes(tracer: ITracer):
    span = tracer.start_span("test_attributes_span")
    span.set_attribute("user_id", 123)
    span.set_attribute("operation", "read")
    assert span.attributes["user_id"] == 123
    assert span.attributes["operation"] == "read"
    span.end()


@pytest.mark.asyncio
async def test_span_record_exception(tracer: ITracer):
    span = tracer.start_span("test_exception_span")
    try:
        raise ValueError("Test exception")
    except ValueError as e:
        span.record_exception(e, {"error.code": 500})

    assert len(span.events) == 1
    event = span.events[0]
    assert event["attributes"]["event.name"] == "exception"
    assert event["attributes"]["exception.type"] == "ValueError"
    assert event["attributes"]["exception.message"] == "Test exception"
    assert event["attributes"]["error.code"] == 500
    span.end()


@pytest.mark.asyncio
async def test_nested_spans(tracer: ITracer):
    parent_span = tracer.start_span("parent_span")
    assert tracer.current_span() == parent_span
    child_span = tracer.start_span("child_span")
    assert tracer.current_span() == child_span
    child_span.end()
    assert tracer.current_span() == parent_span
    parent_span.end()
    assert tracer.current_span() is None


@pytest.mark.asyncio
async def test_get_tracer_singleton():
    tracer1 = get_tracer()
    tracer2 = get_tracer()
    assert tracer1 is tracer2


@pytest.mark.asyncio
async def test_span_end_idempotency(tracer: ITracer):
    span = tracer.start_span("idempotent_span")
    span.end()
    end_time_first = span.end_time
    span.end()  # Calling end again should not change end_time
    assert span.end_time == end_time_first


@pytest.mark.asyncio
async def test_span_context_manager(tracer: ITracer):
    with tracer.start_span("context_manager_span") as span:
        assert tracer.current_span() == span
    assert tracer.current_span() is None
    assert span.end_time is not None


@pytest.mark.asyncio
async def test_span_duration(tracer: ITracer):
    import time
    span = tracer.start_span("duration_span")
    time.sleep(0.01)  # Simulate some work
    span.end()
    assert span.end_time is not None
    assert span.end_time > span.start_time
    assert (span.end_time - span.start_time) >= 0.01


@pytest.mark.asyncio
async def test_span_attributes_after_end(tracer: ITracer):
    span = tracer.start_span("post_end_attributes_span")
    span.end()
    span.set_attribute("status", "completed")
    assert span.attributes["status"] == "completed"


@pytest.mark.asyncio
async def test_span_events_after_end(tracer: ITracer):
    span = tracer.start_span("post_end_events_span")
    span.end()
    span.record_exception(ValueError("Late exception"))
    assert len(span.events) == 1

# Mock for _global_tracer to ensure test isolation


@pytest.fixture(autouse=True)
def reset_global_tracer():
    from src.core.runtime.observability_layer.tracing.tracing import _global_tracer
    _global_tracer.current_span_instance = []
    yield
    _global_tracer.current_span_instance = []
