import pytest
from core.autonomous_intelligence_layer.execution_policies.research_mode_policy import ResearchModePolicy

def test_research_mode_policy_name():
    """اختبار اسم سياسة وضع البحث."""
    policy = ResearchModePolicy()
    assert policy.name == "ResearchMode"

def test_research_mode_policy_apply():
    """اختبار تطبيق سياسة وضع البحث على سياق المهمة."""
    policy = ResearchModePolicy()
    initial_context = {"original_key": "original_value"}
    modified_context = policy.apply(initial_context)
    assert modified_context["execution_mode"] == "ResearchMode"
    assert modified_context["priority"] == "exploratory"
    assert modified_context["resource_allocation"] == "flexible"
    assert modified_context["data_collection"] == "extensive"
    assert modified_context["risk_tolerance"] == "high"
    assert modified_context["original_key"] == "original_value"
    assert initial_context is not modified_context # التأكد من عدم تعديل السياق الأصلي
