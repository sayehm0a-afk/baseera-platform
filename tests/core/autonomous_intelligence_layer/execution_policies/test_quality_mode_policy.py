import pytest
from core.autonomous_intelligence_layer.execution_policies.quality_mode_policy import QualityModePolicy

def test_quality_mode_policy_name():
    """اختبار اسم سياسة وضع الجودة."""
    policy = QualityModePolicy()
    assert policy.name == "QualityMode"

def test_quality_mode_policy_apply():
    """اختبار تطبيق سياسة وضع الجودة على سياق المهمة."""
    policy = QualityModePolicy()
    initial_context = {"original_key": "original_value"}
    modified_context = policy.apply(initial_context)
    assert modified_context["execution_mode"] == "QualityMode"
    assert modified_context["priority"] == "low"
    assert modified_context["resource_allocation"] == "high"
    assert modified_context["accuracy_tolerance"] == "high"
    assert modified_context["original_key"] == "original_value"
    assert initial_context is not modified_context # التأكد من عدم تعديل السياق الأصلي
