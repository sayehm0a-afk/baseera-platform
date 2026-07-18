import pytest
from abc import ABC, abstractmethod
from typing import Any, Dict
from core.autonomous_intelligence_layer.execution_policies.policy import Policy

# فئة وهمية لاختبار الفئة المجردة Policy
class ConcretePolicy(Policy):
    def apply(self, task_context: Dict[str, Any]) -> Dict[str, Any]:
        return {"applied": True, **task_context}

    @property
    def name(self) -> str:
        return "ConcretePolicy"

def test_policy_abstract_methods():
    """اختبار أن الفئة الأساسية Policy مجردة."""
    with pytest.raises(TypeError):
        Policy()

def test_concrete_policy_implementation():
    """اختبار تنفيذ سياسة ملموسة."""
    policy = ConcretePolicy()
    assert policy.name == "ConcretePolicy"
    context = {"data": "test"}
    result = policy.apply(context)
    assert result == {"applied": True, "data": "test"}

def test_policy_repr():
    """اختبار تمثيل السلسلة النصية لـ Policy."""
    policy = ConcretePolicy()
    assert repr(policy) == "ConcretePolicyPolicy()"
