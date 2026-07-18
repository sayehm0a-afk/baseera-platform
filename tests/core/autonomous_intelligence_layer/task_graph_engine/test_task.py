import pytest
from core.autonomous_intelligence_layer.task_graph_engine.task import Task

def test_task_initialization():
    """اختبار تهيئة المهمة الأساسية."""
    task = Task(task_id="task1", payload={"data": "value"})
    assert task.id == "task1"
    assert task.payload == {"data": "value"}
    assert task.agent_id is None
    assert task.status == "PENDING"

def test_task_initialization_with_agent_and_status():
    """اختبار تهيئة المهمة مع وكيل وحالة محددة."""
    task = Task(task_id="task2", payload={"action": "process"}, agent_id="agentX", status="RUNNING")
    assert task.id == "task2"
    assert task.payload == {"action": "process"}
    assert task.agent_id == "agentX"
    assert task.status == "RUNNING"

def test_task_id_validation():
    """اختبار التحقق من صحة معرف المهمة."""
    with pytest.raises(ValueError, match="معرف المهمة \(task_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Task(task_id="", payload={})
    with pytest.raises(ValueError, match="معرف المهمة \(task_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Task(task_id=None, payload={})

def test_payload_validation():
    """اختبار التحقق من صحة حمولة المهمة."""
    with pytest.raises(ValueError, match="حمولة المهمة \(payload\) يجب أن تكون قاموسًا."):
        Task(task_id="task3", payload="invalid_payload")
    with pytest.raises(ValueError, match="حمولة المهمة \(payload\) يجب أن تكون قاموسًا."):
        Task(task_id="task3", payload=None)

def test_agent_id_validation():
    """اختبار التحقق من صحة معرف الوكيل."""
    with pytest.raises(ValueError, match="معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية أو لا شيء."):
        Task(task_id="task4", payload={}, agent_id=123)

def test_status_validation():
    """اختبار التحقق من صحة حالة المهمة."""
    with pytest.raises(ValueError, match="الحالة \(status\) يجب أن تكون سلسلة نصية غير فارغة."):
        Task(task_id="task5", payload={}, status="")
    with pytest.raises(ValueError, match="الحالة \(status\) يجب أن تكون سلسلة نصية غير فارغة."):
        Task(task_id="task5", payload={}, status=None)

def test_update_status():
    """اختبار تحديث حالة المهمة."""
    task = Task(task_id="task6", payload={})
    task.update_status("COMPLETED")
    assert task.status == "COMPLETED"

def test_update_status_validation():
    """اختبار التحقق من صحة الحالة الجديدة عند التحديث."""
    task = Task(task_id="task7", payload={})
    with pytest.raises(ValueError, match="الحالة الجديدة \(new_status\) يجب أن تكون سلسلة نصية غير فارغة."):
        task.update_status("")
    with pytest.raises(ValueError, match="الحالة الجديدة \(new_status\) يجب أن تكون سلسلة نصية غير فارغة."):
        task.update_status(None)

def test_assign_agent():
    """اختبار تعيين وكيل للمهمة."""
    task = Task(task_id="task8", payload={})
    task.assign_agent("agentY")
    assert task.agent_id == "agentY"

def test_assign_agent_validation():
    """اختبار التحقق من صحة معرف الوكيل عند التعيين."""
    task = Task(task_id="task9", payload={})
    with pytest.raises(ValueError, match="معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        task.assign_agent("")
    with pytest.raises(ValueError, match="معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        task.assign_agent(None)

def test_task_to_dict():
    """اختبار تحويل المهمة إلى قاموس."""
    task = Task(task_id="task10", payload={"key": 123}, agent_id="agentZ", status="FAILED")
    expected_dict = {
        "id": "task10",
        "payload": {"key": 123},
        "agent_id": "agentZ",
        "status": "FAILED"
    }
    assert task.to_dict() == expected_dict

def test_task_from_dict():
    """اختبار إنشاء مهمة من قاموس."""
    task_dict = {
        "id": "task11",
        "payload": {"another_key": "another_value"},
        "agent_id": "agentA",
        "status": "COMPLETED"
    }
    task = Task.from_dict(task_dict)
    assert task.id == "task11"
    assert task.payload == {"another_key": "another_value"}
    assert task.agent_id == "agentA"
    assert task.status == "COMPLETED"

def test_task_from_dict_default_status():
    """اختبار إنشاء مهمة من قاموس بحالة افتراضية."""
    task_dict = {"id": "task12", "payload": {"data": "test"}}
    task = Task.from_dict(task_dict)
    assert task.status == "PENDING"

def test_task_equality():
    """اختبار تساوي كائنين من نوع Task."""
    task1 = Task(task_id="task13", payload={"a": 1}, agent_id="ag1", status="PENDING")
    task2 = Task(task_id="task13", payload={"a": 1}, agent_id="ag1", status="PENDING")
    task3 = Task(task_id="task14", payload={"a": 1}, agent_id="ag1", status="PENDING")
    assert task1 == task2
    assert task1 != task3

def test_task_hashable():
    """اختبار أن كائن Task قابل للتجزئة (hashable)."""
    task1 = Task(task_id="task15", payload={"a": 1})
    task2 = Task(task_id="task15", payload={"a": 1})
    task_set = {task1}
    assert task2 in task_set

def test_task_repr():
    """اختبار تمثيل السلسلة النصية لكائن Task."""
    task = Task(task_id="task16", payload={}, status="NEW")
    assert repr(task) == "Task(id='task16', status='NEW', agent_id='None')"
