"""Unit tests for src.analysis.composite.types."""

from datetime import datetime, timedelta, timezone

import pytest

from src.analysis.composite.types import (
    Agreement,
    CompositeCategory,
    CompositeFactorOutput,
    CompositeResult,
    DataCompleteness,
    Freshness,
    build_envelope,
    classify_freshness,
)
from src.analysis.core.contracts import AnalysisEngineResult, AnalysisOutput


def test_classify_freshness_fresh_at_zero_age():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    assert classify_freshness(now, now=now) == Freshness.FRESH


def test_classify_freshness_fresh_within_default_window():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now - timedelta(hours=12)
    assert classify_freshness(as_of, now=now) == Freshness.FRESH


def test_classify_freshness_aging_just_past_fresh_window():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now - timedelta(days=1, hours=1)
    assert classify_freshness(as_of, now=now) == Freshness.AGING


def test_classify_freshness_aging_at_edge_of_default_window():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now - timedelta(days=30)
    assert classify_freshness(as_of, now=now) == Freshness.AGING


def test_classify_freshness_stale_beyond_default_window():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now - timedelta(days=31)
    assert classify_freshness(as_of, now=now) == Freshness.STALE


def test_classify_freshness_unknown_for_future_timestamp():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now + timedelta(days=1)
    assert classify_freshness(as_of, now=now) == Freshness.UNKNOWN


def test_classify_freshness_respects_custom_windows():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now - timedelta(days=100)
    # Fundamentals are expected to be weeks/months old -- a caller can
    # supply a much wider "fresh" window than the default.
    result = classify_freshness(
        as_of, now=now, fresh_within=timedelta(days=120), aging_within=timedelta(days=200)
    )
    assert result == Freshness.FRESH


def test_build_envelope_computes_freshness_automatically():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    as_of = now - timedelta(hours=1)
    envelope = build_envelope("technical_analysis", result="fake-result", as_of=as_of, now=now)

    assert envelope.engine_name == "technical_analysis"
    assert envelope.result == "fake-result"
    assert envelope.as_of == as_of
    assert envelope.freshness == Freshness.FRESH


def test_composite_factor_output_latest_returns_value():
    output = CompositeFactorOutput(
        name="test_factor",
        category=CompositeCategory.ALIGNMENT,
        value=1.0,
        completeness=DataCompleteness.COMPLETE,
        agreement=Agreement.AGREE,
        contributing_engines=["technical_analysis", "fundamental_analysis"],
        explanation={"rule": "test"},
    )
    assert output.latest() == 1.0
    assert isinstance(output, AnalysisOutput)


def test_composite_factor_output_latest_returns_none_when_undefined():
    output = CompositeFactorOutput(
        name="test_factor",
        category=CompositeCategory.ALIGNMENT,
        value=None,
        completeness=DataCompleteness.INSUFFICIENT,
        agreement=Agreement.UNKNOWN,
        contributing_engines=[],
        explanation={"reason": "no engines supplied"},
    )
    assert output.latest() is None


def test_composite_result_get_and_latest_snapshot():
    factor = CompositeFactorOutput(
        name="test_factor",
        category=CompositeCategory.DATA_QUALITY,
        value=0.75,
        completeness=DataCompleteness.COMPLETE,
        agreement=None,
        contributing_engines=["technical_analysis"],
        explanation={},
    )
    result = CompositeResult(factors={"test_factor": factor})

    assert result.get("test_factor") is factor
    assert result.latest_snapshot() == {"test_factor": 0.75}
    assert isinstance(result, AnalysisEngineResult)


def test_composite_result_get_raises_key_error_for_unknown_factor():
    result = CompositeResult(factors={})
    with pytest.raises(KeyError):
        result.get("does_not_exist")
