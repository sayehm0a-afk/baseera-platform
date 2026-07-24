"""Unit tests for IntelligenceModuleRegistry -- uses a fresh, locally-
constructed registry in every test, never
DEFAULT_INTELLIGENCE_MODULE_REGISTRY, so these tests cannot leak state
into (or be affected by) that shared singleton."""

import pytest

from src.analysis.intelligence.contracts.registry import (
    DEFAULT_INTELLIGENCE_MODULE_REGISTRY,
    IntelligenceModuleRegistry,
    IntelligenceModuleSpec,
    ModuleKind,
)


def _spec(module_id: str, kind: ModuleKind = ModuleKind.MARKET_SCANNER) -> IntelligenceModuleSpec:
    return IntelligenceModuleSpec(
        module_id=module_id,
        name=module_id,
        kind=kind,
        version="0.0.0-test",
        description="test-only spec, never registered into the default registry",
        factory=lambda: object(),
    )


def test_register_and_get_roundtrip():
    registry = IntelligenceModuleRegistry()
    spec = _spec("test.scanner", ModuleKind.MARKET_SCANNER)
    registry.register(spec)
    assert registry.get("test.scanner") is spec


def test_duplicate_module_id_raises():
    registry = IntelligenceModuleRegistry()
    registry.register(_spec("test.dup"))
    with pytest.raises(ValueError):
        registry.register(_spec("test.dup"))


def test_all_specs_returns_every_registered_spec():
    registry = IntelligenceModuleRegistry()
    registry.register(_spec("test.a", ModuleKind.RECOMMENDATION_ENGINE))
    registry.register(_spec("test.b", ModuleKind.RISK_ENGINE))
    assert {spec.module_id for spec in registry.all_specs()} == {"test.a", "test.b"}


def test_specs_for_kind_filters_correctly():
    registry = IntelligenceModuleRegistry()
    registry.register(_spec("test.risk", ModuleKind.RISK_ENGINE))
    registry.register(_spec("test.alert", ModuleKind.ALERT_SYSTEM))
    risk_specs = registry.specs_for_kind(ModuleKind.RISK_ENGINE)
    assert [spec.module_id for spec in risk_specs] == ["test.risk"]


def test_specs_for_kind_returns_empty_list_for_an_unregistered_kind():
    registry = IntelligenceModuleRegistry()
    registry.register(_spec("test.risk", ModuleKind.RISK_ENGINE))
    assert registry.specs_for_kind(ModuleKind.AI_DECISION_LAYER) == []


def test_default_intelligence_module_registry_starts_empty():
    # This is the extension point itself, not populated content -- see
    # this package's __init__.py and integration.py for why nothing
    # registers into it yet.
    assert DEFAULT_INTELLIGENCE_MODULE_REGISTRY.all_specs() == []
