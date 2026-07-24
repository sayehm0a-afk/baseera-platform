"""Unit tests for CouncilEngine: per-expert failure isolation, numeric
bounds validation, status-based visibility, and determinism -- the
same discipline tests/unit/analysis/composite/
test_composite_intelligence_engine.py already established for
CompositeIntelligenceEngine.analyze(), applied here to a fourth,
independent registry/engine pair.
"""

import math

from src.analysis.composite.types import DataCompleteness, Freshness
from src.analysis.experts.council_engine import CouncilEngine
from src.analysis.experts.registry import ExpertRegistry, ExpertSpec
from src.analysis.experts.types import Council, CouncilResult, ExpertDirection, ExpertResult, ExpertStatus


def _result(expert_id, score=0.5, confidence=0.5, status_ok=True):
    return ExpertResult(
        expert_id=expert_id,
        expert_name=expert_id,
        council=Council.TECHNICAL,
        domain="fake",
        symbol="1111",
        as_of=None,
        direction=ExpertDirection.BULLISH if status_ok else ExpertDirection.NEUTRAL,
        normalized_score=score,
        confidence=confidence,
        completeness=DataCompleteness.COMPLETE,
        freshness=Freshness.FRESH,
        evidence=(),
        contributing_metrics=(),
        rule_ids=(),
        warnings=(),
        conflicts=(),
        limitations=(),
        version="1.0.0",
        metadata={},
    )


def _healthy_spec(expert_id="technical.healthy", score=1.0, status=ExpertStatus.PRODUCTION):
    return ExpertSpec(
        expert_id=expert_id,
        name=expert_id,
        council=Council.TECHNICAL,
        domain="fake",
        version="1.0.0",
        status=status,
        required_engines=[],
        contributing_metrics=[],
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=lambda symbol, envelopes: _result(expert_id, score=score),
    )


def _raising_spec(expert_id="technical.broken"):
    def _compute(symbol, envelopes):
        raise RuntimeError("simulated expert bug")

    return ExpertSpec(
        expert_id=expert_id,
        name=expert_id,
        council=Council.TECHNICAL,
        domain="fake",
        version="1.0.0",
        status=ExpertStatus.PRODUCTION,
        required_engines=[],
        contributing_metrics=[],
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=_compute,
    )


def _out_of_bounds_spec(expert_id="technical.malformed", score=None, confidence=0.5):
    return ExpertSpec(
        expert_id=expert_id,
        name=expert_id,
        council=Council.TECHNICAL,
        domain="fake",
        version="1.0.0",
        status=ExpertStatus.PRODUCTION,
        required_engines=[],
        contributing_metrics=[],
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=lambda symbol, envelopes: _result(expert_id, score=score, confidence=confidence),
    )


def test_analyze_returns_council_result():
    registry = ExpertRegistry()
    registry.register(_healthy_spec())
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert isinstance(result, CouncilResult)
    assert result.council is Council.TECHNICAL
    assert result.get("technical.healthy").normalized_score == 1.0


def test_a_raising_expert_is_isolated_as_insufficient_not_propagated():
    registry = ExpertRegistry()
    registry.register(_raising_spec())
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    output = result.get("technical.broken")
    assert output.normalized_score is None
    assert output.confidence == 0.0
    assert output.completeness == DataCompleteness.INSUFFICIENT
    assert output.metadata["error_type"] == "RuntimeError"
    assert "simulated expert bug" in output.metadata["error_message"]


def test_other_experts_still_compute_when_one_expert_raises():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.before", score=0.3))
    registry.register(_raising_spec())
    registry.register(_healthy_spec("technical.after", score=-0.4))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert set(result.experts.keys()) == {"technical.before", "technical.broken", "technical.after"}
    assert result.get("technical.before").normalized_score == 0.3
    assert result.get("technical.after").normalized_score == -0.4
    assert result.get("technical.broken").completeness == DataCompleteness.INSUFFICIENT


def test_out_of_range_normalized_score_is_isolated():
    registry = ExpertRegistry()
    registry.register(_out_of_bounds_spec(score=1.5))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    output = result.get("technical.malformed")
    assert output.completeness == DataCompleteness.INSUFFICIENT
    assert "ValueError" in output.metadata["error_type"]


def test_nan_confidence_is_isolated():
    registry = ExpertRegistry()
    registry.register(_out_of_bounds_spec(score=0.5, confidence=math.nan))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert result.get("technical.malformed").completeness == DataCompleteness.INSUFFICIENT


def test_out_of_range_but_finite_confidence_is_isolated():
    registry = ExpertRegistry()
    registry.register(_out_of_bounds_spec(score=0.5, confidence=1.5))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert result.get("technical.malformed").completeness == DataCompleteness.INSUFFICIENT


def test_infinite_score_is_isolated():
    registry = ExpertRegistry()
    registry.register(_out_of_bounds_spec(score=math.inf))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert result.get("technical.malformed").completeness == DataCompleteness.INSUFFICIENT


def test_none_score_with_valid_confidence_is_not_isolated():
    # normalized_score=None is the documented INSUFFICIENT sentinel, not
    # a bounds violation -- must not be isolated by _validate_bounds.
    registry = ExpertRegistry()
    registry.register(_out_of_bounds_spec(score=None, confidence=0.0))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    output = result.get("technical.malformed")
    assert output.normalized_score is None
    assert "error_type" not in output.metadata


def test_disabled_expert_is_never_returned():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.disabled", status=ExpertStatus.DISABLED))
    registry.register(_healthy_spec("technical.enabled", status=ExpertStatus.PRODUCTION))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert set(result.experts.keys()) == {"technical.enabled"}


def test_experimental_expert_excluded_by_default():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.experimental", status=ExpertStatus.EXPERIMENTAL))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {})

    assert result.experts == {}


def test_experimental_expert_included_with_include_all_statuses():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.experimental", status=ExpertStatus.EXPERIMENTAL))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {}, include_all_statuses=True)

    assert set(result.experts.keys()) == {"technical.experimental"}


def test_disabled_expert_excluded_even_with_include_all_statuses():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.disabled", status=ExpertStatus.DISABLED))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    result = engine.analyze("1111", {}, include_all_statuses=True)

    assert result.experts == {}


def test_council_engine_never_touches_other_councils_experts():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.a"))
    fundamental_spec = ExpertSpec(
        expert_id="fundamental.a",
        name="fundamental.a",
        council=Council.FUNDAMENTAL,
        domain="fake",
        version="1.0.0",
        status=ExpertStatus.PRODUCTION,
        required_engines=[],
        contributing_metrics=[],
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=lambda symbol, envelopes: _result("fundamental.a"),
    )
    registry.register(fundamental_spec)

    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)
    result = engine.analyze("1111", {})

    assert set(result.experts.keys()) == {"technical.a"}


def test_analyze_is_deterministic_across_repeated_runs():
    registry = ExpertRegistry()
    registry.register(_healthy_spec("technical.a", score=0.2))
    registry.register(_raising_spec("technical.b"))
    registry.register(_healthy_spec("technical.c", score=-0.8))
    engine = CouncilEngine(council=Council.TECHNICAL, registry=registry)

    first = engine.analyze("1111", {}).latest_snapshot()
    second = engine.analyze("1111", {}).latest_snapshot()

    assert first == second == {"technical.a": 0.2, "technical.b": None, "technical.c": -0.8}
