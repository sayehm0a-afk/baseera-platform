"""Unit tests for IntelligenceComponentRegistry -- mirrors
tests/unit/analysis/experts/test_registry.py's shape exactly. Uses a
fresh, locally-constructed registry in every test, never
DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY, so these tests cannot leak
state into (or be affected by) that shared singleton -- the same
discipline the BEIF registry tests already observe.
"""

import pytest

from src.core.autonomous_intelligence_layer.contracts.registry import (
    DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY,
    IntelligenceComponentRegistry,
    IntelligenceComponentSpec,
)
from src.core.autonomous_intelligence_layer.contracts.types import ComponentKind, ComponentLifecycleStatus


def _spec(component_id: str, kind: ComponentKind = ComponentKind.CUSTOM) -> IntelligenceComponentSpec:
    return IntelligenceComponentSpec(
        component_id=component_id,
        name=component_id,
        kind=kind,
        version="0.0.0-test",
        status=ComponentLifecycleStatus.PROPOSED,
        description="test-only spec, never registered into the default registry",
        factory=lambda: object(),
    )


def test_register_and_get_roundtrip():
    registry = IntelligenceComponentRegistry()
    spec = _spec("test.supervisor", ComponentKind.SUPERVISOR)
    registry.register(spec)
    assert registry.get("test.supervisor") is spec


def test_duplicate_component_id_raises():
    registry = IntelligenceComponentRegistry()
    registry.register(_spec("test.dup"))
    with pytest.raises(ValueError):
        registry.register(_spec("test.dup"))


def test_all_specs_returns_every_registered_spec():
    registry = IntelligenceComponentRegistry()
    registry.register(_spec("test.a", ComponentKind.PLANNER))
    registry.register(_spec("test.b", ComponentKind.DEBATE))
    assert {spec.component_id for spec in registry.all_specs()} == {"test.a", "test.b"}


def test_specs_for_kind_filters_correctly():
    registry = IntelligenceComponentRegistry()
    registry.register(_spec("test.planner", ComponentKind.PLANNER))
    registry.register(_spec("test.debate", ComponentKind.DEBATE))
    planners = registry.specs_for_kind(ComponentKind.PLANNER)
    assert [spec.component_id for spec in planners] == ["test.planner"]


def test_specs_for_kind_returns_empty_list_for_an_unregistered_kind():
    registry = IntelligenceComponentRegistry()
    registry.register(_spec("test.planner", ComponentKind.PLANNER))
    assert registry.specs_for_kind(ComponentKind.VOTING) == []


def test_default_intelligence_component_registry_starts_empty():
    # This is the extension point itself, not populated content -- see
    # this package's __init__.py and integration.py for why nothing
    # registers into it yet.
    assert DEFAULT_INTELLIGENCE_COMPONENT_REGISTRY.all_specs() == []
