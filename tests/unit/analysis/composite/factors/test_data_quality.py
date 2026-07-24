"""Unit tests for src.analysis.composite.factors.data_quality."""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.factors.data_quality import compute_data_quality_summary
from src.analysis.composite.registry import DEFAULT_COMPOSITE_REGISTRY
from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness


def _envelope(engine_name, freshness):
    return EngineResultEnvelope(
        engine_name=engine_name,
        result="fake-result",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        freshness=freshness,
    )


def test_empty_envelopes_is_insufficient():
    output = compute_data_quality_summary({})
    assert output.value is None
    assert output.completeness == DataCompleteness.INSUFFICIENT
    assert output.contributing_engines == []


def test_all_fresh_gives_value_one():
    envelopes = {
        "technical_analysis": _envelope("technical_analysis", Freshness.FRESH),
        "fundamental_analysis": _envelope("fundamental_analysis", Freshness.FRESH),
    }
    output = compute_data_quality_summary(envelopes)
    assert output.value == pytest.approx(1.0)
    assert output.completeness == DataCompleteness.COMPLETE


def test_all_stale_gives_value_zero():
    envelopes = {
        "technical_analysis": _envelope("technical_analysis", Freshness.STALE),
        "fundamental_analysis": _envelope("fundamental_analysis", Freshness.STALE),
    }
    output = compute_data_quality_summary(envelopes)
    assert output.value == pytest.approx(0.0)


def test_half_fresh_gives_value_half():
    envelopes = {
        "technical_analysis": _envelope("technical_analysis", Freshness.FRESH),
        "fundamental_analysis": _envelope("fundamental_analysis", Freshness.STALE),
    }
    output = compute_data_quality_summary(envelopes)
    assert output.value == pytest.approx(0.5)


def test_contributing_engines_sorted():
    envelopes = {
        "fundamental_analysis": _envelope("fundamental_analysis", Freshness.FRESH),
        "technical_analysis": _envelope("technical_analysis", Freshness.FRESH),
    }
    output = compute_data_quality_summary(envelopes)
    assert output.contributing_engines == ["fundamental_analysis", "technical_analysis"]


def test_explanation_reports_freshness_by_engine():
    envelopes = {
        "technical_analysis": _envelope("technical_analysis", Freshness.FRESH),
        "fundamental_analysis": _envelope("fundamental_analysis", Freshness.AGING),
    }
    output = compute_data_quality_summary(envelopes)
    assert output.explanation["freshness_by_engine"] == {
        "technical_analysis": "fresh",
        "fundamental_analysis": "aging",
    }
    assert output.explanation["total_engines"] == 2
    assert output.explanation["fresh_count"] == 1


def test_factor_is_registered_with_default_registry():
    names = {spec.name for spec in DEFAULT_COMPOSITE_REGISTRY.all_specs()}
    assert "data_quality_summary" in names
