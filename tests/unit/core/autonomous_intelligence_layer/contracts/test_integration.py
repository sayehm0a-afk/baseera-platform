"""Unit tests for build_intelligence_context -- the one convenience
constructor integration.py provides. Pure data-shaping, so these are
straightforward construction/roundtrip tests, mirroring how
test_composite_types.py-style tests treat build_envelope."""

from datetime import datetime, timezone

from src.core.autonomous_intelligence_layer.contracts.integration import build_intelligence_context
from src.core.autonomous_intelligence_layer.contracts.types import IntelligenceContext


def test_build_intelligence_context_returns_an_intelligence_context():
    now = datetime.now(timezone.utc)
    context = build_intelligence_context(engine_results={"technical_council": "opaque"}, as_of=now)
    assert isinstance(context, IntelligenceContext)
    assert context.engine_results == {"technical_council": "opaque"}
    assert context.as_of == now


def test_build_intelligence_context_defaults_symbol_and_history():
    now = datetime.now(timezone.utc)
    context = build_intelligence_context(engine_results={}, as_of=now)
    assert context.symbol is None
    assert context.history == ()
    assert context.metadata == {}


def test_build_intelligence_context_passes_through_symbol_history_and_metadata():
    now = datetime.now(timezone.utc)
    context = build_intelligence_context(
        engine_results={},
        as_of=now,
        symbol="2222",
        history=(),
        metadata={"source": "test"},
    )
    assert context.symbol == "2222"
    assert context.metadata == {"source": "test"}


def test_build_intelligence_context_does_not_fetch_or_compute_anything():
    # It only packages what's passed in -- no I/O, no default engine
    # results conjured from nowhere.
    now = datetime.now(timezone.utc)
    context = build_intelligence_context(engine_results={"x": 1}, as_of=now)
    assert context.engine_results == {"x": 1}
