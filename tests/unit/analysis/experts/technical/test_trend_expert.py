"""Unit tests for Trend Expert (src.analysis.experts.technical.
trend_expert). Uses lightweight fake AnalysisEngineResult-conforming
stand-ins, the same technique
tests/unit/analysis/composite/factors/test_trend_fundamental_alignment.py
already uses -- fast, focused, proves this expert depends only on the
structural contract, never on a real TechnicalAnalysisEngine run.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY
from src.analysis.experts.technical.trend_expert import EXPERT_ID, compute_trend_expert
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


def _envelopes(sma=None, ema=None, adx=None, supertrend_direction=None, as_of=None, freshness=Freshness.FRESH):
    outputs = {}
    if sma is not None:
        outputs["sma_20"] = _FakeOutput(sma)
    if ema is not None:
        outputs["ema_20"] = _FakeOutput(ema)
    if adx is not None:
        outputs["adx_14"] = _FakeOutput(adx)
    if supertrend_direction is not None:
        outputs["supertrend"] = _FakeOutput({"trend": 100.0, "direction": supertrend_direction})
    return {"technical_analysis": _envelope(outputs, as_of=as_of, freshness=freshness)}


# ---------------------------------------------------------------------------
# Reference-value tests: hand-computed expected output for known inputs.
# ---------------------------------------------------------------------------


def test_full_agreement_strong_uptrend():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=40.0, supertrend_direction=1.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.8)  # avg_sign(1.0) * strength(40/50=0.8)
    assert result.confidence == pytest.approx(0.9)  # completeness(1.0) * agreement(1.0), capped at ceiling
    assert result.completeness == DataCompleteness.COMPLETE
    assert result.conflicts == ()


def test_full_agreement_strong_downtrend():
    envelopes = _envelopes(sma=10.0, ema=8.0, adx=40.0, supertrend_direction=-1.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BEARISH
    assert result.normalized_score == pytest.approx(-0.8)
    assert result.confidence == pytest.approx(0.9)


def test_directional_conflict_produces_mixed_with_reduced_confidence():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=40.0, supertrend_direction=-1.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.direction == ExpertDirection.MIXED
    assert result.normalized_score == pytest.approx(0.0)
    assert len(result.conflicts) == 1
    assert "disagree" in result.conflicts[0]
    # Disagreement is punished harder than agreement is rewarded (BIIC Article III.3):
    # 0.4 agreement factor vs. the 1.0 factor a fully-agreeing case gets.
    assert result.confidence == pytest.approx(0.4)


def test_weak_adx_scales_down_strength_but_not_direction():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=5.0, supertrend_direction=1.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.1)  # 1.0 * (5/50)
    assert result.confidence == pytest.approx(0.9)  # confidence tracks agreement/completeness, not ADX magnitude


def test_confidence_never_reaches_the_ceiling_of_one():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=100.0, supertrend_direction=1.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.confidence < 1.0
    assert result.confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Missing / partial evidence handling.
# ---------------------------------------------------------------------------


def test_full_agreement_but_very_weak_adx_reads_neutral():
    # Full directional agreement, but ADX is so low the scaled magnitude
    # falls inside the no-clear-trend epsilon band -- NEUTRAL, not BULLISH,
    # and distinctly not MIXED, since there is no actual disagreement here.
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=1.0, supertrend_direction=1.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.conflicts == ()
    assert result.normalized_score == pytest.approx(0.02)  # 1.0 * (1/50)
    assert result.direction == ExpertDirection.NEUTRAL


def test_missing_technical_analysis_envelope_is_insufficient():
    result = compute_trend_expert("1111", {})

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert "not supplied" in result.warnings[0]


def test_partial_evidence_only_ema_sma_available():
    envelopes = _envelopes(sma=10.0, ema=12.0)

    result = compute_trend_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(0.5)  # 1.0 * default 0.5 strength (ADX unavailable)
    assert result.confidence == pytest.approx(0.35)  # completeness(0.5) * single-source agreement(0.7)
    assert any("adx_14" in warning for warning in result.warnings)
    assert any("supertrend" in warning for warning in result.warnings)


def test_no_metrics_available_at_all_is_insufficient():
    envelopes = _envelopes()  # technical_analysis envelope present, but empty

    result = compute_trend_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0


def test_malformed_supertrend_value_never_raises():
    envelopes = {
        "technical_analysis": _envelope(
            {
                "sma_20": _FakeOutput(10.0),
                "ema_20": _FakeOutput(12.0),
                "adx_14": _FakeOutput(40.0),
                "supertrend": _FakeOutput(42.0),  # not a dict -- malformed, must degrade gracefully
            }
        )
    }

    result = compute_trend_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert any("supertrend" in warning for warning in result.warnings)


def test_none_latest_value_treated_as_missing():
    envelopes = {
        "technical_analysis": _envelope(
            {
                "sma_20": _FakeOutput(None),
                "ema_20": _FakeOutput(12.0),
                "adx_14": _FakeOutput(40.0),
                "supertrend": _FakeOutput({"trend": 100.0, "direction": 1.0}),
            }
        )
    }

    result = compute_trend_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.PARTIAL
    assert any("sma_20" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# Evidence / metadata / freshness propagation.
# ---------------------------------------------------------------------------


def test_evidence_items_cite_the_metrics_they_used():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=40.0, supertrend_direction=1.0)

    result = compute_trend_expert("1111", envelopes)

    metric_names = {item.metric_name for item in result.evidence}
    assert metric_names == {"ema_20_vs_sma_20", "supertrend", "adx_14"}
    for item in result.evidence:
        assert -1.0 <= item.contribution <= 1.0


def test_as_of_and_freshness_come_from_the_envelope_not_now():
    as_of = datetime(2020, 1, 1, tzinfo=timezone.utc)
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=40.0, supertrend_direction=1.0, as_of=as_of, freshness=Freshness.STALE)

    result = compute_trend_expert("1111", envelopes)

    assert result.as_of == as_of
    assert result.freshness == Freshness.STALE


def test_symbol_is_propagated_unchanged():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=40.0, supertrend_direction=1.0)

    result = compute_trend_expert("2222", envelopes)

    assert result.symbol == "2222"


def test_contributing_metrics_always_lists_all_four_required_metrics():
    # Declared, static contract -- independent of which were actually
    # available for this specific computation (that distinction lives
    # in `warnings`, not `contributing_metrics`).
    result = compute_trend_expert("1111", {})
    assert set(result.contributing_metrics) == {"sma_20", "ema_20", "adx_14", "supertrend"}


def test_result_is_deterministic_across_repeated_calls():
    envelopes = _envelopes(sma=10.0, ema=12.0, adx=40.0, supertrend_direction=1.0)

    first = compute_trend_expert("1111", envelopes)
    second = compute_trend_expert("1111", envelopes)

    assert first.normalized_score == second.normalized_score
    assert first.confidence == second.confidence
    assert first.direction == second.direction


def test_limitations_disclose_the_deferred_market_structure_gap():
    # Uses _envelopes() (envelope present, no metrics inside it) rather than
    # {} -- the {} case short-circuits through the "no envelope at all" path,
    # which is a different, deliberately minimal INSUFFICIENT sentinel (see
    # test_missing_technical_analysis_envelope_is_insufficient); this test
    # is about the limitations disclosure the main computation path always
    # attaches, regardless of how much evidence was actually available.
    result = compute_trend_expert("1111", _envelopes())
    assert any("Market Structure" in limitation for limitation in result.limitations)


# ---------------------------------------------------------------------------
# Registration.
# ---------------------------------------------------------------------------


def test_trend_expert_is_registered_with_default_registry():
    spec = DEFAULT_EXPERT_REGISTRY.get(EXPERT_ID)
    assert spec.council is Council.TECHNICAL
    assert spec.domain == "trend"
    assert spec.status is ExpertStatus.EXPERIMENTAL
    assert spec.required_engines == ["technical_analysis"]
    assert spec.compute is compute_trend_expert
