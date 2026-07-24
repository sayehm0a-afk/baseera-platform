"""Unit tests for
src.analysis.composite.factors.valuation_momentum_context.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.factors.valuation_momentum_context import (
    compute_valuation_momentum_context,
)
from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY
from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness


class _FakeOutput:
    def __init__(self, value):
        self._value = value

    def latest(self):
        return self._value


class _FakeEngineResult:
    def __init__(self, outputs):
        self._outputs = outputs

    def get(self, name):
        return self._outputs[name]

    def latest_snapshot(self):
        return {name: output.latest() for name, output in self._outputs.items()}


def _envelope(engine_name, result):
    return EngineResultEnvelope(
        engine_name=engine_name,
        result=result,
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        freshness=Freshness.FRESH,
    )


def _technical_envelope(rsi):
    return _envelope("technical_analysis", _FakeEngineResult({"rsi_14": _FakeOutput(rsi)}))


def _fundamental_envelope(pe):
    return _envelope("fundamental_analysis", _FakeEngineResult({"price_to_earnings": _FakeOutput(pe)}))


def test_reference_value_is_normalized_rsi():
    envelopes = {
        "technical_analysis": _technical_envelope(65.0),
        "fundamental_analysis": _fundamental_envelope(18.5),
    }
    output = compute_valuation_momentum_context(envelopes)
    assert output.value == pytest.approx(0.65)
    assert output.completeness == DataCompleteness.COMPLETE
    assert output.agreement is None


def test_pe_carried_in_explanation_not_blended_into_value():
    envelopes = {
        "technical_analysis": _technical_envelope(40.0),
        "fundamental_analysis": _fundamental_envelope(120.0),
    }
    output = compute_valuation_momentum_context(envelopes)
    assert output.value == pytest.approx(0.40)
    assert output.explanation["fundamental_analysis.price_to_earnings"] == 120.0


def test_missing_fundamental_engine_is_partial():
    envelopes = {"technical_analysis": _technical_envelope(50.0)}
    output = compute_valuation_momentum_context(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_missing_technical_engine_is_partial():
    envelopes = {"fundamental_analysis": _fundamental_envelope(20.0)}
    output = compute_valuation_momentum_context(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_no_engines_at_all_is_insufficient():
    output = compute_valuation_momentum_context({})
    assert output.value is None
    assert output.completeness == DataCompleteness.INSUFFICIENT


def test_none_rsi_value_is_partial():
    # rsi_14 present but its own value is None (e.g. warm-up period)
    envelopes = {
        "technical_analysis": _technical_envelope(None),
        "fundamental_analysis": _fundamental_envelope(20.0),
    }
    output = compute_valuation_momentum_context(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_none_price_to_earnings_value_is_partial():
    # price_to_earnings undefined (e.g. no market price supplied to FundamentalAnalysisEngine)
    envelopes = {
        "technical_analysis": _technical_envelope(50.0),
        "fundamental_analysis": _fundamental_envelope(None),
    }
    output = compute_valuation_momentum_context(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_factor_is_registered_with_default_registry():
    names = {spec.name for spec in DEFAULT_COMPOSITE_REGISTRY.all_specs()}
    assert "valuation_momentum_context" in names
