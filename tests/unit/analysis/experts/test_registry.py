"""Unit tests for ExpertRegistry -- mirrors
tests/unit/analysis/composite/test_registry.py's structure for the
sibling CompositeFactorRegistry.
"""

import pytest

from src.analysis.composite.types import DataCompleteness, Freshness
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY, ExpertRegistry, ExpertSpec
from src.analysis.experts.types import Council, ExpertDirection, ExpertResult, ExpertStatus


def _fake_compute(symbol, envelopes):
    return ExpertResult(
        expert_id="technical.fake",
        expert_name="Fake Expert",
        council=Council.TECHNICAL,
        domain="fake",
        symbol=symbol,
        as_of=None,
        direction=ExpertDirection.NEUTRAL,
        normalized_score=None,
        confidence=0.0,
        completeness=DataCompleteness.INSUFFICIENT,
        freshness=Freshness.UNKNOWN,
        evidence=(),
        contributing_metrics=(),
        rule_ids=(),
        warnings=(),
        conflicts=(),
        limitations=(),
        version="1.0.0",
        metadata={},
    )


def _spec(expert_id="technical.fake", council=Council.TECHNICAL, status=ExpertStatus.PRODUCTION):
    return ExpertSpec(
        expert_id=expert_id,
        name="Fake Expert",
        council=council,
        domain="fake",
        version="1.0.0",
        status=status,
        required_engines=["technical_analysis"],
        contributing_metrics=["sma_20"],
        supported_markets=["TASI"],
        supported_timeframes=["daily"],
        execution_priority=0,
        compute=_fake_compute,
    )


def test_register_and_get():
    registry = ExpertRegistry()
    spec = _spec()
    registry.register(spec)

    assert registry.get("technical.fake") is spec


def test_duplicate_registration_raises():
    registry = ExpertRegistry()
    registry.register(_spec())

    with pytest.raises(ValueError):
        registry.register(_spec())


def test_all_specs_returns_every_registered_spec():
    registry = ExpertRegistry()
    registry.register(_spec("technical.a"))
    registry.register(_spec("technical.b"))

    assert {spec.expert_id for spec in registry.all_specs()} == {"technical.a", "technical.b"}


def test_specs_for_council_filters_by_council():
    registry = ExpertRegistry()
    registry.register(_spec("technical.a", council=Council.TECHNICAL))
    registry.register(_spec("fundamental.a", council=Council.FUNDAMENTAL))

    technical_specs = registry.specs_for_council(Council.TECHNICAL)
    assert [spec.expert_id for spec in technical_specs] == ["technical.a"]


def test_specs_for_council_empty_when_no_experts_registered():
    registry = ExpertRegistry()
    assert registry.specs_for_council(Council.RISK) == []


def test_default_registry_contains_trend_expert():
    # Importing src.analysis.experts.technical.trend_expert (transitively,
    # via any test module that imports it) registers "technical.trend"
    # into DEFAULT_EXPERT_REGISTRY as a side effect -- this test proves
    # it, using the same shared-singleton-registry convention every
    # other *Registry in this codebase already relies on.
    import src.analysis.experts.technical  # noqa: F401

    assert DEFAULT_EXPERT_REGISTRY.get("technical.trend").council is Council.TECHNICAL
