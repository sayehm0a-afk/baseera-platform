import pytest
from src.core.autonomous_intelligence_layer.execution_policies.research_mode_policy import ResearchModePolicy

def test_research_mode_policy_name():
    policy = ResearchModePolicy()
    assert policy.name == "ResearchMode"

def test_research_mode_policy_apply():
    policy = ResearchModePolicy()
    task_context = {"initial_setting": "value"}
    modified_context = policy.apply(task_context)

    assert modified_context["execution_mode"] == "ResearchMode"
    assert modified_context["priority"] == "exploratory"
    assert modified_context["resource_allocation"] == "flexible"
    assert modified_context["data_collection"] == "extensive"
    assert modified_context["risk_tolerance"] == "high"
    assert modified_context["initial_setting"] == "value"
