"""Unit tests for Momentum Expert (src.analysis.experts.technical.
momentum_expert). Same lightweight fake-envelope technique as
test_trend_expert.py.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY
from src.analysis.experts.technical.momentum_expert import EXPERT_ID, compute_momentum_expert
from src.analysis.experts.types import Council, ExpertDirection, ExpertStatus


class _FakeOutput:
    def __init__(self, value):
        self._value = value

    def latest(self):
        return self._value


class _FakeTechnicalResult:
    def __init__(self, outputs):
        self._outputs = outputs

    def get(self, name):
        return self._outputs[name]


def _envelope(outputs, as_of=None, freshness=Freshness.FRESH):
    return EngineResultEnvelope(
        engine_name="technical_analysis",
        result=_FakeTechnicalResult(outputs),
        as_of=as_of or datetime(2026, 1, 1, tzinfo=timezone.utc),
        freshness=freshness,
    )


def _envelopes(rsi=None, macd_histogram=None, as_of=None, freshness=Freshness.FRESH):
    outputs = {}
    if rsi is not None:
        outputs["rsi_14"] = _FakeOutput(rsi)
    if macd_histogram is not None:
        outputs["macd"] = _FakeOutput({"macd_line": 1.0, "signal_line": 1.0 - macd_histogram, "histogram": macd_histogram})
    return {"technical_analysis": _envelope(outputs, as_of=as_of, freshness=freshness)}


# ---------------------------------------------------------------------------
# Reference-value tests.
# ---------------------------------------------------------------------------


def test_full_agreement_bullish():
    envelopes = _envelopes(rsi=70.0, macd_histogram=2.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.7)  # avg(0.4, 1.0)
    assert result.confidence == pytest.approx(0.9)
    assert result.completeness == DataCompleteness.COMPLETE
    assert result.conflicts == ()
    assert any("overbought" in warning for warning in result.warnings)


def test_full_agreement_bearish():
    envelopes = _envelopes(rsi=30.0, macd_histogram=-2.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BEARISH
    assert result.normalized_score == pytest.approx(-0.7)  # avg(-0.4, -1.0)
    assert result.confidence == pytest.approx(0.9)
    assert any("oversold" in warning for warning in result.warnings)


def test_directional_conflict_produces_mixed_with_reduced_confidence():
    envelopes = _envelopes(rsi=70.0, macd_histogram=-2.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.direction == ExpertDirection.MIXED
    assert result.normalized_score == pytest.approx(-0.3)  # avg(0.4, -1.0)
    assert len(result.conflicts) == 1
    assert "disagree" in result.conflicts[0]
    assert result.confidence == pytest.approx(0.4)


def test_neutral_rsi_does_not_manufacture_a_conflict():
    # RSI exactly at the midpoint contributes a zero sign -- must not be
    # treated as "disagreeing" with a clearly-signed MACD histogram.
    envelopes = _envelopes(rsi=50.0, macd_histogram=2.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.conflicts == ()
    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.5)  # avg(0.0, 1.0)


def test_rsi_extremes_do_not_flip_the_score_the_naive_way():
    # A very high RSI must read as strong bullish MOMENTUM, never as a
    # bearish "overbought, so sell" call -- the specific misapplication
    # Document 1 Section 5.2 identifies as RSI's most common failure mode.
    envelopes = _envelopes(rsi=95.0, macd_histogram=2.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.normalized_score > 0.0
    assert result.direction == ExpertDirection.BULLISH


def test_confidence_never_reaches_the_ceiling_of_one():
    envelopes = _envelopes(rsi=100.0, macd_histogram=5.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.confidence < 1.0
    assert result.confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Missing / partial evidence handling.
# ---------------------------------------------------------------------------


def test_weak_agreement_within_epsilon_reads_neutral():
    # RSI barely off the midpoint, MACD histogram exactly flat -- agreement
    # (no conflict), but too weak to call a direction either way.
    envelopes = _envelopes(rsi=52.0, macd_histogram=0.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.conflicts == ()
    assert result.normalized_score == pytest.approx(0.02)  # avg(0.04, 0.0)
    assert result.direction == ExpertDirection.NEUTRAL


def test_missing_technical_analysis_envelope_is_insufficient():
    result = compute_momentum_expert("1111", {})

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert "not supplied" in result.warnings[0]


def test_partial_evidence_only_rsi_available():
    envelopes = _envelopes(rsi=80.0)

    result = compute_momentum_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.6)  # (80-50)/50
    assert result.confidence == pytest.approx(0.35)  # completeness(0.5) * single-source(0.7)
    assert any("macd" in warning for warning in result.warnings)


def test_no_metrics_available_at_all_is_insufficient():
    envelopes = _envelopes()

    result = compute_momentum_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0


def test_malformed_macd_value_never_raises():
    envelopes = {
        "technical_analysis": _envelope(
            {
                "rsi_14": _FakeOutput(60.0),
                "macd": _FakeOutput(42.0),  # not a dict -- malformed, must degrade gracefully
            }
        )
    }

    result = compute_momentum_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert any("macd" in warning for warning in result.warnings)


def test_none_latest_value_treated_as_missing():
    envelopes = {
        "technical_analysis": _envelope(
            {
                "rsi_14": _FakeOutput(None),
                "macd": _FakeOutput({"macd_line": 1.0, "signal_line": 0.5, "histogram": 0.5}),
            }
        )
    }

    result = compute_momentum_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert any("rsi_14" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# Evidence / metadata / freshness propagation.
# ---------------------------------------------------------------------------


def test_evidence_items_cite_the_metrics_they_used():
    envelopes = _envelopes(rsi=70.0, macd_histogram=2.0)

    result = compute_momentum_expert("1111", envelopes)

    metric_names = {item.metric_name for item in result.evidence}
    assert metric_names == {"rsi_14", "macd"}
    for item in result.evidence:
        assert -1.0 <= item.contribution <= 1.0


def test_as_of_and_freshness_come_from_the_envelope_not_now():
    as_of = datetime(2020, 1, 1, tzinfo=timezone.utc)
    envelopes = _envelopes(rsi=70.0, macd_histogram=2.0, as_of=as_of, freshness=Freshness.STALE)

    result = compute_momentum_expert("1111", envelopes)

    assert result.as_of == as_of
    assert result.freshness == Freshness.STALE


def test_symbol_is_propagated_unchanged():
    envelopes = _envelopes(rsi=70.0, macd_histogram=2.0)

    result = compute_momentum_expert("2222", envelopes)

    assert result.symbol == "2222"


def test_contributing_metrics_always_lists_both_required_metrics():
    result = compute_momentum_expert("1111", {})
    assert set(result.contributing_metrics) == {"rsi_14", "macd"}


def test_result_is_deterministic_across_repeated_calls():
    envelopes = _envelopes(rsi=70.0, macd_histogram=2.0)

    first = compute_momentum_expert("1111", envelopes)
    second = compute_momentum_expert("1111", envelopes)

    assert first.normalized_score == second.normalized_score
    assert first.confidence == second.confidence
    assert first.direction == second.direction


def test_limitations_disclose_the_no_trend_cross_check_and_macd_scaling_gaps():
    result = compute_momentum_expert("1111", _envelopes())
    assert any("Signal Engine" in limitation for limitation in result.limitations)
    assert any("magnitude" in limitation for limitation in result.limitations)


# ---------------------------------------------------------------------------
# Registration.
# ---------------------------------------------------------------------------


def test_momentum_expert_is_registered_with_default_registry():
    spec = DEFAULT_EXPERT_REGISTRY.get(EXPERT_ID)
    assert spec.council is Council.TECHNICAL
    assert spec.domain == "momentum"
    assert spec.status is ExpertStatus.EXPERIMENTAL
    assert spec.required_engines == ["technical_analysis"]
    assert spec.compute is compute_momentum_expert


def test_momentum_and_trend_experts_have_disjoint_contributing_metrics():
    # BEIF Section 6/16's double-counting guard: two Technical Council
    # experts must never answer their question from an identical metric
    # set -- a direct, registry-level check, not just a design intention.
    momentum_spec = DEFAULT_EXPERT_REGISTRY.get("technical.momentum")
    trend_spec = DEFAULT_EXPERT_REGISTRY.get("technical.trend")

    assert set(momentum_spec.contributing_metrics).isdisjoint(set(trend_spec.contributing_metrics))
