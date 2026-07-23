from src.core.autonomous_intelligence_layer.execution_policies.fast_mode_policy import FastModePolicy


def test_fast_mode_policy_name():
    policy = FastModePolicy()
    assert policy.name == "FastMode"


def test_fast_mode_policy_apply():
    policy = FastModePolicy()
    task_context = {"initial_setting": "value"}
    modified_context = policy.apply(task_context)

    assert modified_context["execution_mode"] == "FastMode"
    assert modified_context["priority"] == "high"
    assert modified_context["resource_allocation"] == "minimal"
    assert modified_context["accuracy_tolerance"] == "low"
    assert modified_context["initial_setting"] == "value"
