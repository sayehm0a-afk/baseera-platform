"""Unit tests for src.analysis.composite.registry -- the composite
factor extension point.
"""

import pytest

from src.analysis.composite.registry import (
    DEFAULT_COMPOSITE_REGISTRY,
    CompositeFactorRegistry,
    CompositeFactorSpec,
)
from src.analysis.composite.types import CompositeCategory, CompositeFactorOutput, DataCompleteness


def _fake_compute(envelopes):
    return CompositeFactorOutput(
        name="fake_factor",
        category=CompositeCategory.DATA_QUALITY,
        value=1.0,
        completeness=DataCompleteness.COMPLETE,
        agreement=None,
        contributing_engines=list(envelopes.keys()),
        explanation={},
    )


def test_register_and_all_specs():
    registry = CompositeFactorRegistry()
    registry.register(
        CompositeFactorSpec("fake_factor", CompositeCategory.DATA_QUALITY, [], _fake_compute)
    )

    specs = registry.all_specs()
    assert len(specs) == 1
    assert specs[0].name == "fake_factor"
    assert specs[0].compute({}).value == 1.0


def test_register_rejects_duplicate_factor_names():
    registry = CompositeFactorRegistry()
    registry.register(CompositeFactorSpec("dup", CompositeCategory.ALIGNMENT, [], _fake_compute))

    with pytest.raises(ValueError, match="dup"):
        registry.register(CompositeFactorSpec("dup", CompositeCategory.CONTEXT, [], _fake_compute))


def test_empty_registry_has_no_specs():
    registry = CompositeFactorRegistry()
    assert registry.all_specs() == []


def test_required_engines_is_preserved_on_the_spec():
    registry = CompositeFactorRegistry()
    registry.register(
        CompositeFactorSpec(
            "fake_factor",
            CompositeCategory.ALIGNMENT,
            ["technical_analysis", "fundamental_analysis"],
            _fake_compute,
        )
    )

    spec = registry.all_specs()[0]
    assert spec.required_engines == ["technical_analysis", "fundamental_analysis"]


def test_default_composite_registry_is_a_real_registry_instance():
    # Populated incrementally by each factor module's self-registration
    # as those commits land; this test only checks the shared
    # singleton's type/identity, not its contents.
    assert isinstance(DEFAULT_COMPOSITE_REGISTRY, CompositeFactorRegistry)
