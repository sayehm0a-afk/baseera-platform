"""Unit tests for Volatility Expert (src.analysis.experts.technical.
volatility_expert). Same lightweight fake-envelope technique as
test_trend_expert.py / test_momentum_expert.py.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY
from src.analysis.experts.technical.volatility_expert import EXPERT_ID, compute_volatility_expert
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


def _envelopes(
    upper=None, middle=None, lower=None, atr=None, bollinger_raw=None, as_of=None, freshness=Freshness.FRESH
):
    outputs = {}
    if bollinger_raw is not None:
        outputs["bollinger"] = _FakeOutput(bollinger_raw)
    elif upper is not None or middle is not None or lower is not None:
        outputs["bollinger"] = _FakeOutput({"upper": upper, "middle": middle, "lower": lower})
    if atr is not None:
        outputs["atr_14"] = _FakeOutput(atr)
    return {"technical_analysis": _envelope(outputs, as_of=as_of, freshness=freshness)}


# ---------------------------------------------------------------------------
# Reference-value tests.
# ---------------------------------------------------------------------------


def test_both_measures_available_and_agree():
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.normalized_score == pytest.approx(0.125)  # avg(0.2, 0.05)
    assert result.confidence == pytest.approx(0.9)
    assert result.completeness == DataCompleteness.COMPLETE
    assert result.conflicts == ()


def test_direction_is_always_neutral_regardless_of_intensity():
    # Architectural Decision 1: volatility has no direction. Even a very
    # high intensity reading must never be reported as bullish or bearish.
    envelopes = _envelopes(upper=200.0, middle=100.0, lower=0.0, atr=50.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score > 0.5


def test_extreme_bandwidth_is_clamped_to_one():
    # (300 - 0) / 100 = 3.0, must clamp to the [0, 1] safety bound, never
    # exceed it and never be asserted as a calibrated "expanded" reading.
    envelopes = _envelopes(upper=300.0, middle=100.0, lower=0.0, atr=1.0)

    result = compute_volatility_expert("1111", envelopes)

    assert 0.0 <= result.normalized_score <= 1.0


def test_confidence_never_reaches_the_ceiling_of_one():
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.confidence < 1.0
    assert result.confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Missing / partial evidence handling.
# ---------------------------------------------------------------------------


def test_missing_technical_analysis_envelope_is_insufficient():
    result = compute_volatility_expert("1111", {})

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert "not supplied" in result.warnings[0]


def test_no_metrics_available_at_all_is_insufficient():
    envelopes = _envelopes()

    result = compute_volatility_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None
    assert result.confidence == 0.0


def test_only_bollinger_available_is_partial_single_source():
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert result.normalized_score == pytest.approx(0.2)
    assert result.confidence == pytest.approx(0.35)  # completeness(0.5) * single-source(0.7)


def test_atr_alone_without_bollinger_cannot_be_normalized():
    # ATR has no price-level reference without a usable Bollinger middle
    # band -- must degrade to INSUFFICIENT, never silently use ATR's raw,
    # price-scale-dependent value as intensity evidence.
    envelopes = _envelopes(atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None
    assert any("normalized" in warning for warning in result.warnings)


def test_zero_middle_band_disables_both_measures():
    envelopes = _envelopes(upper=110.0, middle=0.0, lower=90.0, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None
    assert any("zero" in warning for warning in result.warnings)


def test_degenerate_upper_below_lower_disables_bandwidth_but_not_atr():
    envelopes = _envelopes(upper=90.0, middle=100.0, lower=110.0, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    # Bandwidth is unusable (malformed input), but ATR can still use the
    # valid middle band as its price-level reference -- partial, not total,
    # degradation.
    assert result.completeness == DataCompleteness.PARTIAL
    assert result.normalized_score == pytest.approx(0.05)  # atr(5.0)/middle(100.0) only
    assert any("malformed" in warning or "below" in warning for warning in result.warnings)


def test_bollinger_with_no_middle_band_field_cannot_be_used():
    envelopes = _envelopes(bollinger_raw={"upper": 110.0, "middle": None, "lower": 90.0}, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert any("no defined middle band" in warning for warning in result.warnings)


def test_bollinger_with_valid_middle_but_missing_upper_band():
    envelopes = _envelopes(bollinger_raw={"upper": None, "middle": 100.0, "lower": 90.0}, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    # ATR can still use the valid middle band -- only bandwidth is unusable.
    assert result.completeness == DataCompleteness.PARTIAL
    assert result.normalized_score == pytest.approx(0.05)  # atr(5.0)/middle(100.0) only
    assert any("missing an upper or lower band" in warning for warning in result.warnings)


def test_malformed_bollinger_value_never_raises():
    envelopes = _envelopes(bollinger_raw=42.0, atr=5.0)  # not a dict

    result = compute_volatility_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert any("expected" in warning for warning in result.warnings)


def test_none_latest_value_treated_as_missing():
    envelopes = {
        "technical_analysis": _envelope(
            {
                "bollinger": _FakeOutput(None),
                "atr_14": _FakeOutput(5.0),
            }
        )
    }

    result = compute_volatility_expert("1111", envelopes)

    assert any("bollinger" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# Evidence / metadata / freshness propagation.
# ---------------------------------------------------------------------------


def test_evidence_items_cite_the_metrics_they_used():
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0)

    result = compute_volatility_expert("1111", envelopes)

    metric_names = {item.metric_name for item in result.evidence}
    assert metric_names == {"bollinger", "atr_14"}
    for item in result.evidence:
        assert 0.0 <= item.contribution <= 1.0


def test_as_of_and_freshness_come_from_the_envelope_not_now():
    as_of = datetime(2020, 1, 1, tzinfo=timezone.utc)
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0, as_of=as_of, freshness=Freshness.STALE)

    result = compute_volatility_expert("1111", envelopes)

    assert result.as_of == as_of
    assert result.freshness == Freshness.STALE


def test_symbol_is_propagated_unchanged():
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0)

    result = compute_volatility_expert("2222", envelopes)

    assert result.symbol == "2222"


def test_contributing_metrics_always_lists_both_required_metrics():
    result = compute_volatility_expert("1111", {})
    assert set(result.contributing_metrics) == {"bollinger", "atr_14"}


def test_result_is_deterministic_across_repeated_calls():
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0)

    first = compute_volatility_expert("1111", envelopes)
    second = compute_volatility_expert("1111", envelopes)

    assert first.normalized_score == second.normalized_score
    assert first.confidence == second.confidence
    assert first.direction == second.direction


def test_limitations_disclose_non_directionality_no_threshold_and_risk_boundary():
    result = compute_volatility_expert("1111", _envelopes())
    limitations_text = " ".join(result.limitations)
    assert "NEUTRAL" in limitations_text
    assert "calibrated" in limitations_text
    assert "Risk Council" in limitations_text


def test_conflicts_is_always_empty_by_design():
    # There is no directional-disagreement concept for a non-directional
    # measure -- this expert must never populate `conflicts`, structurally.
    envelopes = _envelopes(upper=110.0, middle=100.0, lower=90.0, atr=5.0)
    result = compute_volatility_expert("1111", envelopes)
    assert result.conflicts == ()


# ---------------------------------------------------------------------------
# Registration.
# ---------------------------------------------------------------------------


def test_volatility_expert_is_registered_with_default_registry():
    spec = DEFAULT_EXPERT_REGISTRY.get(EXPERT_ID)
    assert spec.council is Council.TECHNICAL
    assert spec.domain == "volatility"
    assert spec.status is ExpertStatus.EXPERIMENTAL
    assert spec.required_engines == ["technical_analysis"]
    assert spec.compute is compute_volatility_expert


def test_volatility_expert_metrics_are_disjoint_from_trend_and_momentum():
    # BEIF Section 6/16's double-counting guard, extended to all three
    # Technical Council experts that now exist.
    volatility_spec = DEFAULT_EXPERT_REGISTRY.get("technical.volatility")
    trend_spec = DEFAULT_EXPERT_REGISTRY.get("technical.trend")
    momentum_spec = DEFAULT_EXPERT_REGISTRY.get("technical.momentum")

    volatility_metrics = set(volatility_spec.contributing_metrics)
    assert volatility_metrics.isdisjoint(set(trend_spec.contributing_metrics))
    assert volatility_metrics.isdisjoint(set(momentum_spec.contributing_metrics))
