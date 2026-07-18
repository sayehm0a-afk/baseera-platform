import pytest
from core.autonomous_intelligence_layer.agent_registry.agent_registry import AgentRegistry
from core.autonomous_intelligence_layer.agent_registry.agent import Agent

@pytest.fixture
def agent_registry():
    """Fixture لتوفير مثيل نظيف لـ AgentRegistry لكل اختبار."""
    return AgentRegistry()

@pytest.fixture
def sample_agents():
    """Fixture لتوفير وكلاء عينة."""
    agent1 = Agent("agent1", ["data_analysis", "reporting"], "IDLE")
    agent2 = Agent("agent2", ["planning", "execution"], "BUSY")
    agent3 = Agent("agent3", ["reporting"], "IDLE")
    agent4 = Agent("agent4", ["data_analysis"], "OFFLINE")
    return [agent1, agent2, agent3, agent4]

def test_agent_registry_initialization(agent_registry):
    """اختبار تهيئة AgentRegistry."""
    assert len(agent_registry) == 0

def test_register_agent(agent_registry, sample_agents):
    """اختبار تسجيل وكيل."""
    agent = sample_agents[0]
    agent_registry.register_agent(agent)
    assert len(agent_registry) == 1
    assert agent_registry.get_agent(agent.id) == agent

def test_register_agent_duplicate(agent_registry, sample_agents):
    """اختبار تسجيل وكيل مكرر يرفع خطأ."""
    agent = sample_agents[0]
    agent_registry.register_agent(agent)
    with pytest.raises(ValueError, match=f"الوكيل ذو المعرف {agent.id} مسجل بالفعل."):
        agent_registry.register_agent(agent)

def test_register_agent_invalid_type(agent_registry):
    """اختبار تسجيل كائن ليس من نوع Agent يرفع خطأ."""
    with pytest.raises(ValueError, match="الوكيل يجب أن يكون من نوع Agent."):
        agent_registry.register_agent("not_an_agent")

def test_unregister_agent(agent_registry, sample_agents):
    """اختبار إلغاء تسجيل وكيل."""
    agent = sample_agents[0]
    agent_registry.register_agent(agent)
    agent_registry.unregister_agent(agent.id)
    assert len(agent_registry) == 0
    with pytest.raises(ValueError):
        agent_registry.get_agent(agent.id)

def test_unregister_agent_non_existent(agent_registry):
    """اختبار إلغاء تسجيل وكيل غير موجود يرفع خطأ."""
    with pytest.raises(ValueError, match=r"الوكيل ذو المعرف non_existent_agent غير مسجل."):
        agent_registry.unregister_agent("non_existent_agent")

def test_unregister_agent_invalid_id(agent_registry):
    """اختبار إلغاء تسجيل بمعرف غير صالح يرفع خطأ."""
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        agent_registry.unregister_agent("")
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        agent_registry.unregister_agent(None)

def test_get_agent(agent_registry, sample_agents):
    """اختبار استرداد وكيل."""
    agent = sample_agents[0]
    agent_registry.register_agent(agent)
    retrieved_agent = agent_registry.get_agent(agent.id)
    assert retrieved_agent == agent

def test_get_agent_non_existent(agent_registry):
    """اختبار استرداد وكيل غير موجود يرفع خطأ."""
    with pytest.raises(ValueError, match=r"الوكيل ذو المعرف non_existent_agent غير موجود."):
        agent_registry.get_agent("non_existent_agent")

def test_get_agent_invalid_id(agent_registry):
    """اختبار استرداد بمعرف غير صالح يرفع خطأ."""
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        agent_registry.get_agent("")
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        agent_registry.get_agent(None)

def test_discover_agents_all(agent_registry, sample_agents):
    """اختبار اكتشاف جميع الوكلاء."""
    for agent in sample_agents:
        agent_registry.register_agent(agent)
    discovered = agent_registry.discover_agents()
    assert len(discovered) == len(sample_agents)
    assert set(discovered) == set(sample_agents)

def test_discover_agents_by_capability(agent_registry, sample_agents):
    """اختبار اكتشاف الوكلاء بالقدرة."""
    for agent in sample_agents:
        agent_registry.register_agent(agent)
    discovered = agent_registry.discover_agents(capabilities=["reporting"])
    assert len(discovered) == 2
    assert sample_agents[0] in discovered # agent1 has reporting
    assert sample_agents[2] in discovered # agent3 has reporting
    assert sample_agents[1] not in discovered
    assert sample_agents[3] not in discovered

def test_discover_agents_by_status(agent_registry, sample_agents):
    """اختبار اكتشاف الوكلاء بالحالة."""
    for agent in sample_agents:
        agent_registry.register_agent(agent)
    discovered = agent_registry.discover_agents(status="IDLE")
    assert len(discovered) == 2
    assert sample_agents[0] in discovered # agent1 is IDLE
    assert sample_agents[2] in discovered # agent3 is IDLE
    assert sample_agents[1] not in discovered
    assert sample_agents[3] not in discovered

def test_discover_agents_by_capability_and_status(agent_registry, sample_agents):
    """اختبار اكتشاف الوكلاء بالقدرة والحالة."""
    for agent in sample_agents:
        agent_registry.register_agent(agent)
    discovered = agent_registry.discover_agents(capabilities=["data_analysis"], status="IDLE")
    assert len(discovered) == 1
    assert sample_agents[0] in discovered # agent1 has data_analysis and is IDLE
    assert sample_agents[3] not in discovered # agent4 has data_analysis but is OFFLINE

def test_update_agent_status(agent_registry, sample_agents):
    """اختبار تحديث حالة وكيل مسجل."""
    agent = sample_agents[0]
    agent_registry.register_agent(agent)
    agent_registry.update_agent_status(agent.id, "ACTIVE")
    updated_agent = agent_registry.get_agent(agent.id)
    assert updated_agent.status == "ACTIVE"

def test_update_agent_status_non_existent(agent_registry):
    """اختبار تحديث حالة وكيل غير موجود يرفع خطأ."""
    with pytest.raises(ValueError, match=r"الوكيل ذو المعرف non_existent_agent غير موجود."):
        agent_registry.update_agent_status("non_existent_agent", "ACTIVE")

def test_agent_registry_len(agent_registry, sample_agents):
    """اختبار دالة len لسجل الوكلاء."""
    assert len(agent_registry) == 0
    agent_registry.register_agent(sample_agents[0])
    assert len(agent_registry) == 1

def test_agent_registry_contains(agent_registry, sample_agents):
    """اختبار دالة contains لسجل الوكلاء."""
    agent = sample_agents[0]
    agent_registry.register_agent(agent)
    assert agent.id in agent_registry
    assert "non_existent_agent" not in agent_registry

def test_agent_registry_repr(agent_registry, sample_agents):
    """اختبار تمثيل السلسلة النصية لـ AgentRegistry."""
    agent_registry.register_agent(sample_agents[0])
    repr_str = repr(agent_registry)
    assert "AgentRegistry(registered_agents=1)" in repr_str
