import pytest
from core.autonomous_intelligence_layer.execution_policies.cost_optimized_mode_policy import CostOptimizedModePolicy

def test_cost_optimized_mode_policy_name():
    """اختبار اسم سياسة وضع التكلفة المحسّنة."""
    policy = CostOptimizedModePolicy()
    assert policy.name == "CostOptimizedMode"

def test_cost_optimized_mode_policy_apply():
    """اختبار تطبيق سياسة وضع التكلفة المحسّنة على سياق المهمة."""
    policy = CostOptimizedModePolicy()
    initial_context = {"original_key": "original_value"}
    modified_context = policy.apply(initial_context)
    assert modified_context["execution_mode"] == "CostOptimizedMode"
    assert modified_context["priority"] == "low"
    assert modified_context["resource_allocation"] == "minimal_cost"
    assert modified_context["accuracy_tolerance"] == "flexible"
    assert modified_context["cost_limit"] == "strict"
    assert modified_context["original_key"] == "original_value"
    assert initial_context is not modified_context # التأكد من عدم تعديل السياق الأصلي
