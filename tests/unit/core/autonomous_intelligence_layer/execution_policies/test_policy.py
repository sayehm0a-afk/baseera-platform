import pytest
from src.core.autonomous_intelligence_layer.execution_policies.policy import Policy


class ConcretePolicy(Policy):
    def apply(self, task_context):
        return task_context

    @property
    def name(self):
        return "ConcretePolicy"


def test_policy_is_abstract():
    with pytest.raises(TypeError):
        Policy()


def test_policy_abstract_methods():
    assert "apply" in Policy.__abstractmethods__
    assert "name" in Policy.__abstractmethods__


def test_policy_repr():
    policy = ConcretePolicy()
    assert repr(policy) == "ConcretePolicyPolicy()"
