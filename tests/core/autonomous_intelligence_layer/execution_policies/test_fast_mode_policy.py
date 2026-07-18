import pytest
from core.autonomous_intelligence_layer.execution_policies.fast_mode_policy import FastModePolicy

def test_fast_mode_policy_name():
    """اختبار اسم سياسة الوضع السريع."""
    policy = FastModePolicy()
    assert policy.name == "FastMode"

def test_fast_mode_policy_apply():
    """اختبار تطبيق سياسة الوضع السريع على سياق المهمة."""
    policy = FastModePolicy()
    initial_context = {"original_key": "original_value"}
    modified_context = policy.apply(initial_context)
    assert modified_context["execution_mode"] == "FastMode"
    assert modified_context["priority"] == "high"
    assert modified_context["resource_allocation"] == "minimal"
    assert modified_context["accuracy_tolerance"] == "low"
    assert modified_context["original_key"] == "original_value"
    assert initial_context is not modified_context # التأكد من عدم تعديل السياق الأصلي
