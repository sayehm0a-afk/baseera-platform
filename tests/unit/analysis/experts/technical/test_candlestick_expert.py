"""Unit tests for Candlestick & Price Action Expert (src.analysis.experts.
technical.candlestick_expert). Same lightweight fake-envelope technique
as test_trend_expert.py / test_volume_expert.py, using the real
PatternMatch dataclass directly (trivial, dependency-free) rather than a
fake -- this expert reads .value (List[PatternMatch]) directly, so its
tests need genuine PatternMatch objects, the same reason
test_volume_expert.py needs a genuine pd.Series for obv.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.types import DataCompleteness, EngineResultEnvelope, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY
from src.analysis.experts.technical.candlestick_expert import EXPERT_ID, compute_candlestick_expert
from src.analysis.experts.types import Council, ExpertDirection, ExpertStatus
from src.analysis.types import PatternMatch


class _FakeListOutput:
    """Mirrors IndicatorOutput's `.value` field directly -- this expert
    reads .value, never .latest(), for candlestick_patterns (see module
    docstring, Architectural Decision 1)."""

    def __init__(self, value):
        self.value = value


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


def _envelopes(patterns=None, patterns_raw=None, as_of=None, freshness=Freshness.FRESH):
    outputs = {}
    if patterns_raw is not None:
        outputs["candlestick_patterns"] = _FakeListOutput(patterns_raw)
    elif patterns is not None:
        outputs["candlestick_patterns"] = _FakeListOutput(patterns)
    return {"technical_analysis": _envelope(outputs, as_of=as_of, freshness=freshness)}


_LATEST_TS = datetime(2026, 1, 10, tzinfo=timezone.utc)
_EARLIER_TS = datetime(2026, 1, 5, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Reference-value tests.
# ---------------------------------------------------------------------------


def test_single_hammer_at_latest_bar_is_bullish():
    envelopes = _envelopes(patterns=[PatternMatch("hammer", _LATEST_TS, bullish=True)])

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(1.0)
    assert result.completeness == DataCompleteness.COMPLETE
    # Single directional source -> completeness(1.0) * single-source(0.7).
    assert result.confidence == pytest.approx(0.7)
    assert result.conflicts == ()


def test_single_shooting_star_at_latest_bar_is_bearish():
    envelopes = _envelopes(patterns=[PatternMatch("shooting_star", _LATEST_TS, bullish=False)])

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BEARISH
    assert result.normalized_score == pytest.approx(-1.0)
    assert result.confidence == pytest.approx(0.7)


def test_agreeing_bullish_engulfing_and_hammer_on_same_bar_raises_confidence():
    envelopes = _envelopes(
        patterns=[
            PatternMatch("bullish_engulfing", _LATEST_TS, bullish=True),
            PatternMatch("hammer", _LATEST_TS, bullish=True),
        ]
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(1.0)
    # Two agreeing directional sources -> completeness(1.0) * agreement(1.0).
    assert result.confidence == pytest.approx(0.9)
    assert result.conflicts == ()


def test_disagreeing_patterns_on_same_bar_are_mixed_with_a_conflict():
    envelopes = _envelopes(
        patterns=[
            PatternMatch("hammer", _LATEST_TS, bullish=True),
            PatternMatch("shooting_star", _LATEST_TS, bullish=False),
        ]
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.MIXED
    assert result.normalized_score == pytest.approx(0.0)
    assert len(result.conflicts) == 1
    # Disagreement penalty -> completeness(1.0) * 0.4.
    assert result.confidence == pytest.approx(0.4)


def test_doji_only_at_latest_bar_contributes_no_direction():
    envelopes = _envelopes(patterns=[PatternMatch("doji", _LATEST_TS, bullish=True)])

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert result.completeness == DataCompleteness.COMPLETE  # data was readable, just non-directional
    assert len(result.evidence) == 1
    assert result.evidence[0].contribution == 0.0


def test_doji_alongside_a_directional_pattern_does_not_dilute_the_direction():
    envelopes = _envelopes(
        patterns=[
            PatternMatch("doji", _LATEST_TS, bullish=False),
            PatternMatch("hammer", _LATEST_TS, bullish=True),
        ]
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert result.normalized_score == pytest.approx(1.0)  # average of [+1] only -- doji excluded
    assert len(result.evidence) == 2


def test_earlier_non_latest_patterns_are_ignored():
    envelopes = _envelopes(
        patterns=[
            PatternMatch("shooting_star", _EARLIER_TS, bullish=False),
            PatternMatch("hammer", _LATEST_TS, bullish=True),
        ]
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert result.direction == ExpertDirection.BULLISH
    assert len(result.evidence) == 1
    assert result.evidence[0].observed_value["pattern_name"] == "hammer"


# ---------------------------------------------------------------------------
# Missing / partial / malformed evidence handling.
# ---------------------------------------------------------------------------


def test_missing_technical_analysis_envelope_is_insufficient():
    result = compute_candlestick_expert("1111", {})

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert "not supplied" in result.warnings[0]


def test_missing_candlestick_patterns_entirely_is_insufficient():
    envelopes = {"technical_analysis": _envelope({})}

    result = compute_candlestick_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert result.normalized_score is None
    assert any("candlestick_patterns" in warning for warning in result.warnings)


def test_none_candlestick_patterns_value_never_raises():
    envelopes = {"technical_analysis": _envelope({"candlestick_patterns": _FakeListOutput(None)})}

    result = compute_candlestick_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert any("no defined value" in warning for warning in result.warnings)


def test_non_list_candlestick_patterns_value_never_raises():
    envelopes = _envelopes(patterns_raw="not-a-list")

    result = compute_candlestick_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.INSUFFICIENT
    assert any("not a list" in warning for warning in result.warnings)


def test_empty_pattern_list_is_complete_but_neutral():
    envelopes = _envelopes(patterns=[])

    result = compute_candlestick_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.COMPLETE
    assert result.direction == ExpertDirection.NEUTRAL
    assert result.normalized_score is None
    assert result.confidence == 0.0
    assert any("no candlestick patterns detected" in warning for warning in result.warnings)


def test_incomparable_timestamps_never_raise():
    envelopes = _envelopes(
        patterns=[
            PatternMatch("hammer", "not-a-timestamp", bullish=True),
            PatternMatch("doji", _LATEST_TS, bullish=True),
        ]
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert result.completeness == DataCompleteness.COMPLETE
    assert result.normalized_score is None
    assert any("could not be compared" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# Evidence / metadata / freshness propagation.
# ---------------------------------------------------------------------------


def test_evidence_items_cite_the_metric_they_used():
    envelopes = _envelopes(patterns=[PatternMatch("hammer", _LATEST_TS, bullish=True)])

    result = compute_candlestick_expert("1111", envelopes)

    metric_names = {item.metric_name for item in result.evidence}
    assert metric_names == {"candlestick_patterns"}


def test_as_of_and_freshness_come_from_the_envelope_not_now():
    as_of = datetime(2020, 1, 1, tzinfo=timezone.utc)
    envelopes = _envelopes(
        patterns=[PatternMatch("hammer", _LATEST_TS, bullish=True)], as_of=as_of, freshness=Freshness.STALE
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert result.as_of == as_of
    assert result.freshness == Freshness.STALE


def test_symbol_is_propagated_unchanged():
    envelopes = _envelopes(patterns=[PatternMatch("hammer", _LATEST_TS, bullish=True)])

    result = compute_candlestick_expert("2222", envelopes)

    assert result.symbol == "2222"


def test_contributing_metrics_always_lists_the_one_required_metric():
    result = compute_candlestick_expert("1111", {})
    assert result.contributing_metrics == ("candlestick_patterns",)


def test_result_is_deterministic_across_repeated_calls():
    envelopes = _envelopes(patterns=[PatternMatch("hammer", _LATEST_TS, bullish=True)])

    first = compute_candlestick_expert("1111", envelopes)
    second = compute_candlestick_expert("1111", envelopes)

    assert first.normalized_score == second.normalized_score
    assert first.confidence == second.confidence
    assert first.direction == second.direction


def test_limitations_disclose_staleness_doji_magnitude_and_context_gaps():
    result = compute_candlestick_expert("1111", _envelopes(patterns=[]))
    limitations_text = " ".join(result.limitations)
    assert "true latest bar" in limitations_text
    assert "Doji" in limitations_text
    assert "no magnitude/strength signal" in limitations_text
    assert "context-free bar geometry" in limitations_text


def test_rule_ids_are_prefixed_per_pattern():
    envelopes = _envelopes(
        patterns=[
            PatternMatch("hammer", _LATEST_TS, bullish=True),
            PatternMatch("doji", _LATEST_TS, bullish=False),
        ]
    )

    result = compute_candlestick_expert("1111", envelopes)

    assert set(result.rule_ids) == {"candlestick.hammer", "candlestick.doji"}


# ---------------------------------------------------------------------------
# Registration.
# ---------------------------------------------------------------------------


def test_candlestick_expert_is_registered_with_default_registry():
    spec = DEFAULT_EXPERT_REGISTRY.get(EXPERT_ID)
    assert spec.council is Council.TECHNICAL
    assert spec.domain == "price_action"
    assert spec.status is ExpertStatus.EXPERIMENTAL
    assert spec.required_engines == ["technical_analysis"]
    assert spec.compute is compute_candlestick_expert


def test_candlestick_expert_metrics_are_disjoint_from_all_other_technical_experts():
    candlestick_spec = DEFAULT_EXPERT_REGISTRY.get("technical.candlestick")
    other_ids = ["technical.trend", "technical.momentum", "technical.volatility", "technical.volume"]

    candlestick_metrics = set(candlestick_spec.contributing_metrics)
    for other_id in other_ids:
        other_spec = DEFAULT_EXPERT_REGISTRY.get(other_id)
        assert candlestick_metrics.isdisjoint(set(other_spec.contributing_metrics)), other_id
