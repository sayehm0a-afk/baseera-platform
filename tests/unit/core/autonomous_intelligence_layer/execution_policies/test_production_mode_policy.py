from src.core.autonomous_intelligence_layer.execution_policies.production_mode_policy import ProductionModePolicy


def test_production_mode_policy_name():
    policy = ProductionModePolicy()
    assert policy.name == "ProductionMode"


def test_production_mode_policy_apply():
    policy = ProductionModePolicy()
    task_context = {"initial_setting": "value"}
    modified_context = policy.apply(task_context)

    assert modified_context["execution_mode"] == "ProductionMode"
    assert modified_context["priority"] == "critical"
    assert modified_context["resource_allocation"] == "guaranteed"
    assert modified_context["reliability"] == "high"
    assert modified_context["monitoring"] == "enabled"
    assert modified_context["rollback_strategy"] == "enabled"
    assert modified_context["initial_setting"] == "value"
