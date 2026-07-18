import pytest
from core.autonomous_intelligence_layer.execution_policies.execution_policies import ExecutionPolicies
from core.autonomous_intelligence_layer.execution_policies.policy import Policy
from core.autonomous_intelligence_layer.execution_policies.fast_mode_policy import FastModePolicy
from core.autonomous_intelligence_layer.execution_policies.balanced_mode_policy import BalancedModePolicy
from core.autonomous_intelligence_layer.execution_policies.quality_mode_policy import QualityModePolicy
from core.autonomous_intelligence_layer.execution_policies.cost_optimized_mode_policy import CostOptimizedModePolicy
from core.autonomous_intelligence_layer.execution_policies.research_mode_policy import ResearchModePolicy
from core.autonomous_intelligence_layer.execution_policies.production_mode_policy import ProductionModePolicy

def test_execution_policies_initialization():
    """اختبار تهيئة ExecutionPolicies."""
    policies_manager = ExecutionPolicies()
    assert len(policies_manager._policies) == 6
    assert isinstance(policies_manager._policies["FastMode"], FastModePolicy)
    assert isinstance(policies_manager._policies["BalancedMode"], BalancedModePolicy)
    assert isinstance(policies_manager._policies["QualityMode"], QualityModePolicy)
    assert isinstance(policies_manager._policies["CostOptimizedMode"], CostOptimizedModePolicy)
    assert isinstance(policies_manager._policies["ResearchMode"], ResearchModePolicy)
    assert isinstance(policies_manager._policies["ProductionMode"], ProductionModePolicy)

def test_get_policy_existing():
    """اختبار استرداد سياسة موجودة."""
    policies_manager = ExecutionPolicies()
    policy = policies_manager.get_policy("FastMode")
    assert isinstance(policy, FastModePolicy)
    assert policy.name == "FastMode"

def test_get_policy_non_existent():
    """اختبار استرداد سياسة غير موجودة يرفع خطأ."""
    policies_manager = ExecutionPolicies()
    with pytest.raises(ValueError, match=r"السياسة ‏\'NonExistentPolicy\'‏ غير موجودة. السياسات المتاحة: .*"):
        policies_manager.get_policy("NonExistentPolicy")

def test_list_available_policies():
    """اختبار سرد السياسات المتاحة."""
    policies_manager = ExecutionPolicies()
    available_policies = policies_manager.list_available_policies()
    expected_policies = [
        "FastMode",
        "BalancedMode",
        "QualityMode",
        "CostOptimizedMode",
        "ResearchMode",
        "ProductionMode"
    ]
    assert sorted(available_policies) == sorted(expected_policies)

def test_execution_policies_repr():
    """اختبار تمثيل السلسلة النصية لـ ExecutionPolicies."""
    policies_manager = ExecutionPolicies()
    repr_str = repr(policies_manager)
    assert "ExecutionPolicies(available_policies=" in repr_str
    assert "FastMode" in repr_str
    assert "ProductionMode" in repr_str
