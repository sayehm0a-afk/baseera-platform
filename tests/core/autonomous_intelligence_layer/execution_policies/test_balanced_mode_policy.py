import pytest
from core.autonomous_intelligence_layer.execution_policies.balanced_mode_policy import BalancedModePolicy

def test_balanced_mode_policy_name():
    """اختبار اسم سياسة الوضع المتوازن."""
    policy = BalancedModePolicy()
    assert policy.name == "BalancedMode"

def test_balanced_mode_policy_apply():
    """اختبار تطبيق سياسة الوضع المتوازن على سياق المهمة."""
    policy = BalancedModePolicy()
    initial_context = {"original_key": "original_value"}
    modified_context = policy.apply(initial_context)
    assert modified_context["execution_mode"] == "BalancedMode"
    assert modified_context["priority"] == "medium"
    assert modified_context["resource_allocation"] == "moderate"
    assert modified_context["accuracy_tolerance"] == "medium"
    assert modified_context["original_key"] == "original_value"
    assert initial_context is not modified_context # التأكد من عدم تعديل السياق الأصلي
