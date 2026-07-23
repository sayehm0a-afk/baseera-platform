from src.core.autonomous_intelligence_layer.execution_policies.quality_mode_policy import QualityModePolicy


def test_quality_mode_policy_name():
    policy = QualityModePolicy()
    assert policy.name == "QualityMode"


def test_quality_mode_policy_apply():
    policy = QualityModePolicy()
    task_context = {"initial_setting": "value"}
    modified_context = policy.apply(task_context)

    assert modified_context["execution_mode"] == "QualityMode"
    assert modified_context["priority"] == "low"
    assert modified_context["resource_allocation"] == "high"
    assert modified_context["accuracy_tolerance"] == "high"
    assert modified_context["initial_setting"] == "value"
