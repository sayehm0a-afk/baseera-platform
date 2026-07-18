import pytest
from core.autonomous_intelligence_layer.execution_policies.production_mode_policy import ProductionModePolicy

def test_production_mode_policy_name():
    """اختبار اسم سياسة وضع الإنتاج."""
    policy = ProductionModePolicy()
    assert policy.name == "ProductionMode"

def test_production_mode_policy_apply():
    """اختبار تطبيق سياسة وضع الإنتاج على سياق المهمة."""
    policy = ProductionModePolicy()
    initial_context = {"original_key": "original_value"}
    modified_context = policy.apply(initial_context)
    assert modified_context["execution_mode"] == "ProductionMode"
    assert modified_context["priority"] == "critical"
    assert modified_context["resource_allocation"] == "guaranteed"
    assert modified_context["reliability"] == "high"
    assert modified_context["monitoring"] == "enabled"
    assert modified_context["rollback_strategy"] == "enabled"
    assert modified_context["original_key"] == "original_value"
    assert initial_context is not modified_context # التأكد من عدم تعديل السياق الأصلي
