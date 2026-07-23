import pytest
from src.core.autonomous_intelligence_layer.agent_registry.agent import Agent


@pytest.fixture
def sample_agent():
    return Agent("agent1", ["analyze", "report"], "ACTIVE", {"location": "server_a"})


def test_agent_initialization(sample_agent):
    assert sample_agent.id == "agent1"
    assert sample_agent.capabilities == ["analyze", "report"]
    assert sample_agent.status == "ACTIVE"
    assert sample_agent.metadata == {"location": "server_a"}


def test_agent_initialization_default_status():
    agent = Agent("agent2", ["process"])
    assert agent.status == "IDLE"
    assert agent.metadata == {}


def test_agent_initialization_invalid_agent_id():
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Agent("", ["cap"])
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Agent(123, ["cap"])


def test_agent_initialization_invalid_capabilities():
    with pytest.raises(ValueError, match=r"القدرات \(capabilities\) يجب أن تكون قائمة من السلاسل النصية."):
        Agent("agent3", "not_a_list")
    with pytest.raises(ValueError, match=r"القدرات \(capabilities\) يجب أن تكون قائمة من السلاسل النصية."):
        Agent("agent3", [123])


def test_agent_initialization_invalid_status():
    with pytest.raises(ValueError, match=r"الحالة \(status\) يجب أن تكون سلسلة نصية غير فارغة."):
        Agent("agent4", ["cap"], "")
    with pytest.raises(ValueError, match=r"الحالة \(status\) يجب أن تكون سلسلة نصية غير فارغة."):
        Agent("agent4", ["cap"], 123)


def test_agent_initialization_invalid_metadata():
    with pytest.raises(ValueError, match=r"البيانات الوصفية \(metadata\) يجب أن تكون قاموسًا أو لا شيء."):
        Agent("agent5", ["cap"], metadata="not_a_dict")


def test_update_status(sample_agent):
    sample_agent.update_status("BUSY")
    assert sample_agent.status == "BUSY"


def test_update_status_invalid_status(sample_agent):
    with pytest.raises(ValueError, match=r"الحالة الجديدة \(new_status\) يجب أن تكون سلسلة نصية غير فارغة."):
        sample_agent.update_status("")
    with pytest.raises(ValueError, match=r"الحالة الجديدة \(new_status\) يجب أن تكون سلسلة نصية غير فارغة."):
        sample_agent.update_status(123)


def test_has_capability(sample_agent):
    assert sample_agent.has_capability("analyze") is True
    assert sample_agent.has_capability("report") is True
    assert sample_agent.has_capability("optimize") is False


def test_to_dict(sample_agent):
    expected_dict = {
        "id": "agent1",
        "capabilities": ["analyze", "report"],
        "status": "ACTIVE",
        "metadata": {"location": "server_a"}
    }
    assert sample_agent.to_dict() == expected_dict


def test_from_dict():
    agent_data = {
        "id": "agent_from_dict",
        "capabilities": ["read", "write"],
        "status": "IDLE",
        "metadata": {"version": "1.0"}
    }
    agent = Agent.from_dict(agent_data)
    assert agent.id == "agent_from_dict"
    assert agent.capabilities == ["read", "write"]
    assert agent.status == "IDLE"
    assert agent.metadata == {"version": "1.0"}


def test_from_dict_default_status():
    agent_data = {
        "id": "agent_no_status",
        "capabilities": ["read"]
    }
    agent = Agent.from_dict(agent_data)
    assert agent.status == "IDLE"


def test_eq(sample_agent):
    same_agent = Agent("agent1", ["analyze", "report"], "ACTIVE", {"location": "server_a"})
    different_id = Agent("agent_diff", ["analyze", "report"], "ACTIVE", {"location": "server_a"})
    different_capabilities = Agent("agent1", ["analyze"], "ACTIVE", {"location": "server_a"})
    different_status = Agent("agent1", ["analyze", "report"], "IDLE", {"location": "server_a"})
    different_metadata = Agent("agent1", ["analyze", "report"], "ACTIVE", {"location": "server_b"})

    assert sample_agent == same_agent
    assert sample_agent != different_id
    assert sample_agent != different_capabilities
    assert sample_agent != different_status
    assert sample_agent != different_metadata
    assert sample_agent != "not_an_agent"


def test_hash(sample_agent):
    same_agent = Agent("agent1", ["analyze", "report"], "ACTIVE", {"location": "server_a"})
    different_id = Agent("agent_diff", ["analyze", "report"], "ACTIVE", {"location": "server_a"})

    assert hash(sample_agent) == hash(same_agent)
    assert hash(sample_agent) != hash(different_id)


def test_repr(sample_agent):
    expected_repr = "Agent(id=\'agent1\', status=\'ACTIVE\', capabilities=['analyze', 'report'])"
    assert repr(sample_agent) == expected_repr
