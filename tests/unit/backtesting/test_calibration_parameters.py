"""Unit tests for src.backtesting.calibration.parameters."""

import pytest

from src.analysis.decision.types import AIDecisionTuning
from src.analysis.recommendation.types import RecommendationTuning
from src.backtesting.calibration.parameters import (
    build_ai_tuning,
    build_contributors,
    build_recommendation_tuning,
    build_strategy_kwargs,
)


def test_build_contributors_none_when_no_override():
    assert build_contributors(None) is None
    assert build_contributors({}) is None


def test_build_contributors_overrides_named_weights_only():
    contributors = build_contributors({"technical": 0.4, "risk": 0.2})
    by_name = {c.name: c.default_weight for c in contributors}
    assert by_name["technical"] == 0.4
    assert by_name["risk"] == 0.2
    assert len(contributors) == 9  # every contributor still present, unnamed ones keep engine defaults
    assert by_name["fundamental"] == 0.25  # AIDecisionEngine's own default, untouched


def test_build_contributors_unknown_name_raises():
    with pytest.raises(KeyError):
        build_contributors({"not_a_real_contributor": 0.5})


def test_build_recommendation_tuning_defaults_when_absent():
    assert build_recommendation_tuning({}) == RecommendationTuning()


def test_build_recommendation_tuning_applies_overrides():
    tuning = build_recommendation_tuning({"recommendation_tuning": {"buy_threshold": 58.0}})
    assert tuning.buy_threshold == 58.0
    assert tuning.strong_buy_threshold == 75.0  # untouched field keeps its default


def test_build_recommendation_tuning_unknown_field_raises():
    with pytest.raises(TypeError):
        build_recommendation_tuning({"recommendation_tuning": {"not_a_real_field": 1.0}})


def test_build_ai_tuning_defaults_when_absent():
    assert build_ai_tuning({}) == AIDecisionTuning()


def test_build_ai_tuning_applies_overrides():
    tuning = build_ai_tuning({"ai_tuning": {"stop_atr_multiple": 1.2}})
    assert tuning.stop_atr_multiple == 1.2
    assert tuning.risk_low_threshold == 65.0


def test_build_strategy_kwargs_shape():
    kwargs = build_strategy_kwargs(
        {"contributor_weights": {"technical": 0.4}, "recommendation_tuning": {"buy_threshold": 58.0}},
        name="candidate-x",
    )
    assert kwargs["name"] == "candidate-x"
    assert kwargs["recommendation_tuning"].buy_threshold == 58.0
    assert kwargs["contributors"] is not None
    assert kwargs["ai_tuning"] == AIDecisionTuning()


def test_build_strategy_kwargs_empty_config_is_all_defaults():
    kwargs = build_strategy_kwargs({}, name="baseline")
    assert kwargs["contributors"] is None
    assert kwargs["recommendation_tuning"] == RecommendationTuning()
    assert kwargs["ai_tuning"] == AIDecisionTuning()
