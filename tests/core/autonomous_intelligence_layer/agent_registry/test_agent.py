import pytest
from core.autonomous_intelligence_layer.agent_registry.agent import Agent

def test_agent_initialization():
    """اختبار تهيئة الوكيل الأساسية."""
    agent = Agent(agent_id="agent1", capabilities=["data_analysis", "reporting"])
    assert agent.id == "agent1"
    assert agent.capabilities == ["data_analysis", "reporting"]
    assert agent.status == "IDLE"
    assert agent.metadata == {}

def test_agent_initialization_with_status_and_metadata():
    """اختبار تهيئة الوكيل بحالة وبيانات وصفية محددة."""
    metadata = {"version": "1.0", "location": "cloud"}
    agent = Agent(agent_id="agent2", capabilities=["planning"], status="BUSY", metadata=metadata)
    assert agent.id == "agent2"
    assert agent.capabilities == ["planning"]
    assert agent.status == "BUSY"
    assert agent.metadata == metadata

def test_agent_id_validation():
    """اختبار التحقق من صحة معرف الوكيل."""
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Agent(agent_id="", capabilities=[])
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Agent(agent_id=None, capabilities=[])

def test_capabilities_validation():
    """اختبار التحقق من صحة القدرات."""
    with pytest.raises(ValueError, match=r"القدرات \(capabilities\) يجب أن تكون قائمة من السلاسل النصية."):
        Agent(agent_id="agent3", capabilities="invalid")
    with pytest.raises(ValueError, match=r"القدرات \(capabilities\) يجب أن تكون قائمة من السلاسل النصية."):
        Agent(agent_id="agent3", capabilities=[123])

def test_status_validation():
    """اختبار التحقق من صحة حالة الوكيل."""
    with pytest.raises(ValueError, match=r"الحالة \(status\) يجب أن تكون سلسلة نصية غير فارغة."):
        Agent(agent_id="agent4", capabilities=[], status="")
    with pytest.raises(ValueError, match=r"الحالة \(status\) يجب أن تكون سلسلة نصية غير فارغة."):
        Agent(agent_id="agent4", capabilities=[], status=None)

def test_metadata_validation():
    """اختبار التحقق من صحة البيانات الوصفية."""
    with pytest.raises(ValueError, match=r"البيانات الوصفية \(metadata\) يجب أن تكون قاموسًا أو لا شيء."):
        Agent(agent_id="agent5", capabilities=[], metadata="invalid")

def test_update_status():
    """اختبار تحديث حالة الوكيل."""
    agent = Agent(agent_id="agent6", capabilities=["test"])
    agent.update_status("OFFLINE")
    assert agent.status == "OFFLINE"

def test_update_status_validation():
    """اختبار التحقق من صحة الحالة الجديدة عند التحديث."""
    agent = Agent(agent_id="agent7", capabilities=["test"])
    with pytest.raises(ValueError, match=r"الحالة الجديدة \(new_status\) يجب أن تكون سلسلة نصية غير فارغة."):
        agent.update_status("")
    with pytest.raises(ValueError, match=r"الحالة الجديدة \(new_status\) يجب أن تكون سلسلة نصية غير فارغة."):
        agent.update_status(None)

def test_has_capability():
    """اختبار التحقق من قدرة الوكيل."""
    agent = Agent(agent_id="agent8", capabilities=["read", "write"])
    assert agent.has_capability("read") is True
    assert agent.has_capability("execute") is False

def test_agent_to_dict():
    """اختبار تحويل الوكيل إلى قاموس."""
    metadata = {"env": "prod"}
    agent = Agent(agent_id="agent9", capabilities=["deploy"], status="ACTIVE", metadata=metadata)
    expected_dict = {
        "id": "agent9",
        "capabilities": ["deploy"],
        "status": "ACTIVE",
        "metadata": {"env": "prod"}
    }
    assert agent.to_dict() == expected_dict

def test_agent_from_dict():
    """اختبار إنشاء وكيل من قاموس."""
    agent_dict = {
        "id": "agent10",
        "capabilities": ["monitor"],
        "status": "ERROR",
        "metadata": {"last_error": "timeout"}
    }
    agent = Agent.from_dict(agent_dict)
    assert agent.id == "agent10"
    assert agent.capabilities == ["monitor"]
    assert agent.status == "ERROR"
    assert agent.metadata == {"last_error": "timeout"}

def test_agent_from_dict_default_status():
    """اختبار إنشاء وكيل من قاموس بحالة افتراضية."""
    agent_dict = {"id": "agent11", "capabilities": ["analyze"]}
    agent = Agent.from_dict(agent_dict)
    assert agent.status == "IDLE"

def test_agent_equality():
    """اختبار تساوي كائنين من نوع Agent."""
    agent1 = Agent(agent_id="agent12", capabilities=["cap1"], status="IDLE")
    agent2 = Agent(agent_id="agent12", capabilities=["cap1"], status="IDLE")
    agent3 = Agent(agent_id="agent13", capabilities=["cap2"], status="BUSY")
    assert agent1 == agent2
    assert agent1 != agent3

def test_agent_hashable():
    """اختبار أن كائن Agent قابل للتجزئة (hashable)."""
    agent1 = Agent(agent_id="agent14", capabilities=["capA"])
    agent2 = Agent(agent_id="agent14", capabilities=["capA"])
    agent_set = {agent1}
    assert agent2 in agent_set

def test_agent_repr():
    """اختبار تمثيل السلسلة النصية لكائن Agent."""
    agent = Agent(agent_id="agent15", capabilities=["deploy"], status="ACTIVE")
    assert repr(agent) == "Agent(id=\'agent15\', status=\'ACTIVE\', capabilities=['deploy'])"
