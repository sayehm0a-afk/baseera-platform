"""Unit tests for
src.analysis.composite.factors.trend_fundamental_alignment.

Uses lightweight fake AnalysisEngineResult-conforming stand-ins (the
same technique tests/unit/analysis/core/test_contracts.py uses) rather
than real TechnicalAnalysisEngine/FundamentalAnalysisEngine output --
fast, focused, and proves this factor depends only on the structural
contract, not on either concrete engine. A full real-engine
integration test lives in test_composite_intelligence_engine.py.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.factors.trend_fundamental_alignment import (
    compute_trend_fundamental_alignment,
)
from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY
from src.analysis.composite.types import Agreement, DataCompleteness, EngineResultEnvelope, Freshness


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


def _technical_envelope(direction):
    result = _FakeEngineResult({"supertrend": _FakeOutput({"trend": 100.0, "direction": direction})})
    return _envelope("technical_analysis", result)


def _fundamental_envelope(revenue_growth):
    result = _FakeEngineResult({"revenue_growth": _FakeOutput(revenue_growth)})
    return _envelope("fundamental_analysis", result)


def test_both_bullish_agrees_positive():
    envelopes = {
        "technical_analysis": _technical_envelope(1.0),
        "fundamental_analysis": _fundamental_envelope(0.25),
    }
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value == pytest.approx(1.0)
    assert output.agreement == Agreement.AGREE
    assert output.completeness == DataCompleteness.COMPLETE


def test_both_bearish_agrees_negative():
    envelopes = {
        "technical_analysis": _technical_envelope(-1.0),
        "fundamental_analysis": _fundamental_envelope(-0.1),
    }
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value == pytest.approx(-1.0)
    assert output.agreement == Agreement.AGREE


def test_bullish_technical_bearish_fundamental_disagrees():
    envelopes = {
        "technical_analysis": _technical_envelope(1.0),
        "fundamental_analysis": _fundamental_envelope(-0.1),
    }
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value == pytest.approx(0.0)
    assert output.agreement == Agreement.DISAGREE


def test_flat_revenue_growth_treated_as_disagreement():
    envelopes = {
        "technical_analysis": _technical_envelope(1.0),
        "fundamental_analysis": _fundamental_envelope(0.0),
    }
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value == pytest.approx(0.0)
    assert output.agreement == Agreement.DISAGREE


def test_missing_fundamental_engine_is_partial():
    envelopes = {"technical_analysis": _technical_envelope(1.0)}
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL
    assert output.agreement == Agreement.UNKNOWN
    assert output.contributing_engines == ["technical_analysis"]


def test_missing_technical_engine_is_partial():
    envelopes = {"fundamental_analysis": _fundamental_envelope(0.1)}
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_no_engines_at_all_is_insufficient():
    output = compute_trend_fundamental_alignment({})
    assert output.value is None
    assert output.completeness == DataCompleteness.INSUFFICIENT
    assert output.contributing_engines == []


def test_missing_supertrend_output_on_technical_result_is_partial():
    result = _FakeEngineResult({})  # no "supertrend" key -> KeyError caught internally
    envelopes = {
        "technical_analysis": _envelope("technical_analysis", result),
        "fundamental_analysis": _fundamental_envelope(0.1),
    }
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_never_raises_on_malformed_technical_result():
    # supertrend output present but its .latest() isn't a dict --
    # should degrade to None, not raise.
    result = _FakeEngineResult({"supertrend": _FakeOutput(42.0)})
    envelopes = {
        "technical_analysis": _envelope("technical_analysis", result),
        "fundamental_analysis": _fundamental_envelope(0.1),
    }
    output = compute_trend_fundamental_alignment(envelopes)
    assert output.value is None
    assert output.completeness == DataCompleteness.PARTIAL


def test_factor_is_registered_with_default_registry():
    names = {spec.name for spec in DEFAULT_COMPOSITE_REGISTRY.all_specs()}
    assert "trend_fundamental_alignment" in names
