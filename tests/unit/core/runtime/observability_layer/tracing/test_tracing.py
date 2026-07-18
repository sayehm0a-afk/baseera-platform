import pytest
from core.runtime.observability_layer.tracing.tracing import Tracer, Span, get_tracer, ITracer, ISpan
import time

@pytest.fixture
def tracer() -> ITracer:
    return Tracer()

@pytest.mark.asyncio
async def test_start_span(tracer: ITracer, capsys):
    span = tracer.start_span("test_span")
    assert isinstance(span, ISpan)
    assert tracer.current_span() == span
    captured = capsys.readouterr()
    assert "SPAN STARTED: test_span" in captured.out
    span.end()
    captured = capsys.readouterr()
    assert "SPAN ENDED: test_span" in captured.out
    assert tracer.current_span() is None

@pytest.mark.asyncio
async def test_span_attributes(tracer: ITracer, capsys):
    span = tracer.start_span("attribute_span")
    span.set_attribute("user_id", "123")
    span.set_attribute("operation", "read")
    captured = capsys.readouterr()
    assert "ATTRIBUTE SET: user_id=123" in captured.out
    assert "ATTRIBUTE SET: operation=read" in captured.out
    span.end()

@pytest.mark.asyncio
async def test_span_record_exception(tracer: ITracer, capsys):
    span = tracer.start_span("exception_span")
    try:
        raise ValueError("Test exception")
    except ValueError as e:
        span.record_exception(e, {"error.code": 500})
    captured = capsys.readouterr()
    assert "EXCEPTION RECORDED: Test exception" in captured.out
    span.end()

@pytest.mark.asyncio
async def test_span_duration(tracer: ITracer):
    span = tracer.start_span("duration_span")
    time.sleep(0.01) # Simulate some work
    span.end()
    assert span.end_time is not None
    assert span.end_time > span.start_time

@pytest.mark.asyncio
async def test_get_global_tracer():
    tracer1 = get_tracer()
    tracer2 = get_tracer()
    assert tracer1 is tracer2
    span = tracer1.start_span("global_tracer_span")
    assert tracer1.current_span() == span
    span.end()
    assert tracer1.current_span() is None
