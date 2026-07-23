from src.core.autonomous_intelligence_layer.execution_policies.cost_optimized_mode_policy import CostOptimizedModePolicy


def test_cost_optimized_mode_policy_name():
    policy = CostOptimizedModePolicy()
    assert policy.name == "CostOptimizedMode"


def test_cost_optimized_mode_policy_apply():
    policy = CostOptimizedModePolicy()
    task_context = {"initial_setting": "value"}
    modified_context = policy.apply(task_context)

    assert modified_context["execution_mode"] == "CostOptimizedMode"
    assert modified_context["priority"] == "low"
    assert modified_context["resource_allocation"] == "minimal_cost"
    assert modified_context["accuracy_tolerance"] == "flexible"
    assert modified_context["cost_limit"] == "strict"
    assert modified_context["initial_setting"] == "value"
