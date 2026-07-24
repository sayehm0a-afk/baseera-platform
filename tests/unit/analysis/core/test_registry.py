"""Unit tests for src.analysis.core.registry -- the engine-level
extension point.
"""

import pytest

from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY, EngineRegistry, EngineSpec


class _FakeEngine:
    def analyze(self):
        return "fake result"


def test_register_and_all_specs():
    registry = EngineRegistry()
    registry.register(EngineSpec("fake", "a fake engine for testing", _FakeEngine))

    specs = registry.all_specs()
    assert len(specs) == 1
    assert specs[0].name == "fake"
    assert specs[0].engine_factory() is not None
    assert isinstance(specs[0].engine_factory(), _FakeEngine)


def test_get_returns_the_registered_spec():
    registry = EngineRegistry()
    registry.register(EngineSpec("fake", "a fake engine for testing", _FakeEngine))

    spec = registry.get("fake")
    assert spec.name == "fake"
    assert spec.description == "a fake engine for testing"


def test_get_raises_key_error_for_unknown_engine():
    registry = EngineRegistry()
    with pytest.raises(KeyError):
        registry.get("does_not_exist")


def test_register_rejects_duplicate_engine_names():
    registry = EngineRegistry()
    registry.register(EngineSpec("dup", "first", _FakeEngine))

    with pytest.raises(ValueError, match="dup"):
        registry.register(EngineSpec("dup", "second", _FakeEngine))


def test_empty_registry_has_no_specs():
    registry = EngineRegistry()
    assert registry.all_specs() == []


def test_default_engine_registry_is_a_real_engine_registry_instance():
    # Populated by core/bootstrap.py once both engines exist; this test
    # only checks the shared singleton's type/identity, not its
    # contents (see test_bootstrap.py for that).
    assert isinstance(DEFAULT_ENGINE_REGISTRY, EngineRegistry)
