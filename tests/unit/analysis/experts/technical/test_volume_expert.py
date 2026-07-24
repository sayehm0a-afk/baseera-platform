"""Unit tests for Volume Expert (src.analysis.experts.technical.
volume_expert). Same lightweight fake-envelope technique as
test_trend_expert.py / test_momentum_expert.py / test_volatility_expert.py,
extended with a real pd.Series for OBV -- this expert is the first to
read an indicator's full series rather than only its latest() value,
so the fake must genuinely support .iloc[]/len() the way the real
IndicatorOutput.value (a pd.Series) does.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY
from src.analysis.experts.technical.volume_expert import EXPERT_ID, compute_volume_expert
from src.analysis.experts.types import Council, ExpertDirection, ExpertStatus


class _FakeSeriesOutput:
    """Mirrors IndicatorOutput's `.value` field directly -- this expert
    reads .value, never .latest(), for obv (see module docstring)."""

    def __init__(self, value):
        self.value = value


class _FakeScalarOutput:
    """Mirrors IndicatorOutput's `.latest()` -- used for volume_sma_20,
    which this expert reads the conventional way."""

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


def _envelopes(obv_values=None, obv_raw=None, volume_sma=None, as_of=None, freshness=Freshness.FRESH):
    outputs = {}
    if obv_raw is not None:
        outputs["obv"] = _FakeSeriesOutput(obv_raw)
    elif obv_values is not None:
        outputs["obv"] = _FakeSeriesOutput(pd.Series(obv_values))
    if volume_sma is not None:
        outputs["volume_sma_20"] = _FakeScalarOutput(volume_sma)
    return {"technical_analysis": _envelope(outputs, as_of=as_of, freshness=freshness)}


_RISING_OBV = list(range(25))  # 0, 1, ..., 24 -- steady net accumulation, delta=1.0 every bar
_FALLING_OBV = list(range(25, 0, -1))  # 25, 24, ..., 1 -- steady net distribution, delta=-1.0 every bar


# ---------------------------------------------------------------------------
# Reference-value tests.
# ---------------------------------------------------------------------------


def test_rising_obv_with_average_relative_volume_is_bullish():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    # latest(24) - lookback_20(4) = 20 > 0 -> sign +1.
    # recovered volume |24-23|=1.0; ratio=1.0/1.0=1.0; strength=1/(1+1)=0.5.
    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.5)
    assert result.confidence == pytest.approx(0.9)
    assert result.completeness == DataCompleteness.COMPLETE
    assert result.conflicts == ()


def test_falling_obv_with_average_relative_volume_is_bearish():
    envelopes = _envelopes(obv_values=_FALLING_OBV, volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    # latest(1) - lookback_20(21) = -20 < 0 -> sign -1.
    assert result.direction == ExpertDirection.BEARISH
    assert result.normalized_score == pytest.approx(-0.5)
    assert result.confidence == pytest.approx(0.9)


def test_confidence_never_reaches_the_ceiling_of_one():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    assert result.confidence < 1.0
    assert result.confidence == pytest.approx(0.9)


def test_elevated_relative_volume_scales_the_magnitude_up():
    # Same directional trend, but recovered volume is far above its
    # average -> higher strength than the average-volume case above.
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=0.1)

    result = compute_volume_expert("1111", envelopes)

    # ratio = 1.0/0.1 = 10.0; strength = 10/11.
    assert result.normalized_score == pytest.approx(10.0 / 11.0)
    assert result.direction == ExpertDirection.BULLISH


# ---------------------------------------------------------------------------
# Missing / partial evidence handling.
# ---------------------------------------------------------------------------


def test_missing_technical_analysis_envelope_is_insufficient():
    result = compute_volume_expert("1111", {})

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert "not supplied" in result.warnings[0]


def test_missing_obv_entirely_is_insufficient():
    envelopes = _envelopes(volume_sma=1.0)  # no obv at all

    result = compute_volume_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None
    assert any("obv" in warning for warning in result.warnings)


def test_insufficient_obv_history_for_direction_but_enough_for_relative_volume():
    # Only 10 points -- not enough for the 20-bar lookback, but the
    # 2-point recovered-volume calculation only needs 2.
    envelopes = _envelopes(obv_values=list(range(10)), volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    assert result.normalized_score is None  # no direction -> no score, by design
    assert result.confidence == 0.0
    assert result.completeness == DataCompleteness.PARTIAL  # volume_sma_20 still contributed evidence
    assert any("fewer than 21 data points" in warning for warning in result.warnings)


def test_single_obv_point_is_insufficient_for_everything():
    envelopes = _envelopes(obv_values=[5.0], volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None


def test_missing_volume_sma_20_falls_back_to_default_strength():
    envelopes = _envelopes(obv_values=_RISING_OBV)  # no volume_sma_20

    result = compute_volume_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.5)  # sign(+1) * default strength(0.5)
    assert result.completeness == DataCompleteness.PARTIAL
    assert result.confidence == pytest.approx(0.35)  # completeness(0.5) * single-source(0.7)
    assert any("volume_sma_20" in warning for warning in result.warnings)


def test_zero_volume_sma_20_disables_relative_volume_but_not_direction():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=0.0)

    result = compute_volume_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.5)  # falls back to default strength
    assert any("zero or negative" in warning for warning in result.warnings)


def test_none_volume_sma_20_latest_value_treated_as_missing():
    envelopes = _envelopes(obv_values=_RISING_OBV)
    envelopes["technical_analysis"].result._outputs["volume_sma_20"] = _FakeScalarOutput(None)

    result = compute_volume_expert("1111", envelopes)

    assert any("volume_sma_20" in warning and "no defined latest value" in warning for warning in result.warnings)


def test_malformed_obv_value_never_raises():
    envelopes = _envelopes(obv_raw=42.0, volume_sma=1.0)  # not series-like

    result = compute_volume_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert any("Series-like" in warning for warning in result.warnings)


def test_none_obv_value_never_raises():
    # _FakeSeriesOutput(None) explicitly -- distinct from "obv" being absent
    # entirely, which test_missing_obv_entirely_is_insufficient covers, and
    # not expressible via the _envelopes() helper's `is not None` guards.
    envelopes = {
        "technical_analysis": _envelope(
            {"obv": _FakeSeriesOutput(None), "volume_sma_20": _FakeScalarOutput(1.0)}
        )
    }

    result = compute_volume_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert any("no defined value" in warning for warning in result.warnings)


def test_non_numeric_obv_values_never_raise():
    # A malformed series (e.g. produced by a future, buggy alternate
    # indicator implementation) with a non-numeric latest value must
    # degrade both rules gracefully, never propagate a TypeError/ValueError.
    obv_values = list(range(23)) + ["not-a-number"]
    envelopes = _envelopes(obv_values=obv_values, volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None
    assert any("could not be read as numeric" in warning for warning in result.warnings)


def test_flat_close_recovers_zero_volume_and_warns():
    # Last two OBV values equal -> the latest bar's close was unchanged
    # (or genuinely zero volume traded); recovered volume reads exactly
    # zero either way, per OBV's own known blind spot.
    obv_values = list(range(24)) + [23]  # ..., 22, 23, 23
    envelopes = _envelopes(obv_values=obv_values, volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    assert any("exactly zero" in warning for warning in result.warnings)
    # Direction is still computable (unaffected by the flat last bar), but a
    # zero recovered volume zeroes out the magnitude entirely -> NEUTRAL.
    assert result.normalized_score == pytest.approx(0.0)
    assert result.direction == ExpertDirection.NEUTRAL


# ---------------------------------------------------------------------------
# Evidence / metadata / freshness propagation.
# ---------------------------------------------------------------------------


def test_evidence_items_cite_the_metrics_they_used():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0)

    result = compute_volume_expert("1111", envelopes)

    metric_names = {item.metric_name for item in result.evidence}
    assert metric_names == {"obv", "volume_sma_20"}


def test_as_of_and_freshness_come_from_the_envelope_not_now():
    as_of = datetime(2020, 1, 1, tzinfo=timezone.utc)
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0, as_of=as_of, freshness=Freshness.STALE)

    result = compute_volume_expert("1111", envelopes)

    assert result.as_of == as_of
    assert result.freshness == Freshness.STALE


def test_symbol_is_propagated_unchanged():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0)

    result = compute_volume_expert("2222", envelopes)

    assert result.symbol == "2222"


def test_contributing_metrics_always_lists_both_required_metrics():
    result = compute_volume_expert("1111", {})
    assert set(result.contributing_metrics) == {"obv", "volume_sma_20"}


def test_result_is_deterministic_across_repeated_calls():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0)

    first = compute_volume_expert("1111", envelopes)
    second = compute_volume_expert("1111", envelopes)

    assert first.normalized_score == second.normalized_score
    assert first.confidence == second.confidence
    assert first.direction == second.direction


def test_limitations_disclose_single_source_obv_blindspot_and_no_threshold():
    result = compute_volume_expert("1111", _envelopes())
    limitations_text = " ".join(result.limitations)
    assert "only one directional evidence source" in limitations_text
    assert "OBV" in limitations_text
    assert "calibrated" in limitations_text


def test_conflicts_is_always_empty_by_design():
    envelopes = _envelopes(obv_values=_RISING_OBV, volume_sma=1.0)
    result = compute_volume_expert("1111", envelopes)
    assert result.conflicts == ()


# ---------------------------------------------------------------------------
# Registration.
# ---------------------------------------------------------------------------


def test_volume_expert_is_registered_with_default_registry():
    spec = DEFAULT_EXPERT_REGISTRY.get(EXPERT_ID)
    assert spec.council is Council.TECHNICAL
    assert spec.domain == "volume"
    assert spec.status is ExpertStatus.EXPERIMENTAL
    assert spec.required_engines == ["technical_analysis"]
    assert spec.compute is compute_volume_expert


def test_volume_expert_metrics_are_disjoint_from_trend_momentum_and_volatility():
    volume_spec = DEFAULT_EXPERT_REGISTRY.get("technical.volume")
    trend_spec = DEFAULT_EXPERT_REGISTRY.get("technical.trend")
    momentum_spec = DEFAULT_EXPERT_REGISTRY.get("technical.momentum")
    volatility_spec = DEFAULT_EXPERT_REGISTRY.get("technical.volatility")

    volume_metrics = set(volume_spec.contributing_metrics)
    assert volume_metrics.isdisjoint(set(trend_spec.contributing_metrics))
    assert volume_metrics.isdisjoint(set(momentum_spec.contributing_metrics))
    assert volume_metrics.isdisjoint(set(volatility_spec.contributing_metrics))
