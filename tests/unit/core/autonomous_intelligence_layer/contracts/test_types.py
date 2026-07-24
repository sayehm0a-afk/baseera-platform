"""Unit tests for the AIL contracts' shared value types. All construction
tests, since these are pure data shapes with no logic -- see
test_interfaces.py for structural-satisfaction tests and
test_registry.py for the registry behavior."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from src.core.autonomous_intelligence_layer.contracts.types import (
    AgentIdentity,
    AgentMessage,
    ComponentKind,
    ComponentLifecycleStatus,
    IntelligenceComponentOutput,
    IntelligenceContext,
)


def test_component_kind_has_one_value_per_named_role_plus_custom():
    assert {member.value for member in ComponentKind} == {
        "supervisor",
        "planner",
        "reflection",
        "memory",
        "collaboration",
        "debate",
        "voting",
        "knowledge_graph",
        "self_improvement",
        "custom",
    }


def test_component_lifecycle_status_matches_expert_status_shape_but_is_a_separate_enum():
    from src.analysis.experts.types import ExpertStatus

    assert {member.value for member in ComponentLifecycleStatus} == {
        member.value for member in ExpertStatus
    }
    assert ComponentLifecycleStatus is not ExpertStatus


def test_agent_identity_instance_id_defaults_to_none():
    identity = AgentIdentity(component_id="future.supervisor", kind=ComponentKind.SUPERVISOR, version="0.0.0")
    assert identity.instance_id is None


def test_agent_identity_is_frozen():
    identity = AgentIdentity(component_id="future.supervisor", kind=ComponentKind.SUPERVISOR, version="0.0.0")
    with pytest.raises(FrozenInstanceError):
        identity.component_id = "changed"  # type: ignore[misc]


def test_intelligence_context_metadata_defaults_to_empty_dict_not_shared_across_instances():
    now = datetime.now(timezone.utc)
    a = IntelligenceContext(engine_results={}, as_of=now)
    b = IntelligenceContext(engine_results={}, as_of=now)
    assert a.metadata == {}
    assert a.metadata is not b.metadata  # default_factory, not a shared mutable default


def test_intelligence_context_symbol_and_history_default_appropriately():
    now = datetime.now(timezone.utc)
    context = IntelligenceContext(engine_results={"technical_council": object()}, as_of=now)
    assert context.symbol is None
    assert context.history == ()


def test_intelligence_context_carries_arbitrary_engine_results_without_importing_any_engine_type():
    now = datetime.now(timezone.utc)
    context = IntelligenceContext(
        engine_results={"technical_council": "opaque-result-object"},
        as_of=now,
        symbol="1120",
    )
    assert context.engine_results["technical_council"] == "opaque-result-object"
    assert context.symbol == "1120"


def test_intelligence_component_output_explanation_defaults_to_empty_dict_not_shared():
    identity = AgentIdentity(component_id="future.planner", kind=ComponentKind.PLANNER, version="0.0.0")
    now = datetime.now(timezone.utc)
    a = IntelligenceComponentOutput(identity=identity, kind=ComponentKind.PLANNER, produced_at=now, payload={})
    b = IntelligenceComponentOutput(identity=identity, kind=ComponentKind.PLANNER, produced_at=now, payload={})
    assert a.explanation == {}
    assert a.explanation is not b.explanation


def test_intelligence_component_output_confidence_is_optional_and_unconstrained():
    identity = AgentIdentity(component_id="future.self_improvement", kind=ComponentKind.SELF_IMPROVEMENT, version="0.0.0")
    now = datetime.now(timezone.utc)
    output = IntelligenceComponentOutput(
        identity=identity,
        kind=ComponentKind.SELF_IMPROVEMENT,
        produced_at=now,
        payload={"proposal": "increase lookback window"},
        confidence=None,
    )
    assert output.confidence is None
    assert output.warnings == ()


def test_agent_message_recipients_default_to_empty_tuple_meaning_broadcast():
    sender = AgentIdentity(component_id="future.debate", kind=ComponentKind.DEBATE, version="0.0.0")
    now = datetime.now(timezone.utc)
    message = AgentMessage(sender=sender, kind="opening_statement", payload={"text": "..."}, sent_at=now)
    assert message.recipients == ()
