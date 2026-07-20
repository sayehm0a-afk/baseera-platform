import pytest
from src.core.autonomous_intelligence_layer.task_graph_engine.task import Task, TaskStatus

def test_task_initialization():
    task = Task("task1", {"data": "value"}, "agent1", TaskStatus.RUNNING)
    assert task.id == "task1"
    assert task.payload == {"data": "value"}
    assert task.agent_id == "agent1"
    assert task.status == TaskStatus.RUNNING

def test_task_initialization_default_status():
    task = Task("task2", {"data": "value"})
    assert task.status == TaskStatus.PENDING

def test_task_initialization_no_agent():
    task = Task("task3", {"data": "value"}, None, TaskStatus.COMPLETED)
    assert task.agent_id is None

def test_task_initialization_invalid_task_id():
    with pytest.raises(ValueError, match=r"معرف المهمة \(task_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Task(123, {"data": "value"})
    with pytest.raises(ValueError, match=r"معرف المهمة \(task_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Task("", {"data": "value"})

def test_task_initialization_invalid_payload():
    with pytest.raises(ValueError, match=r"حمولة المهمة \(payload\) يجب أن تكون قاموسًا."):
        Task("task4", "invalid_payload")

def test_task_initialization_invalid_agent_id():
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية أو لا شيء."):
        Task("task5", {"data": "value"}, 123)

def test_task_initialization_invalid_status():
    with pytest.raises(ValueError, match=r"الحالة \(status\) يجب أن تكون من نوع TaskStatus."):
        Task("task6", {"data": "value"}, "agent1", 123)
    with pytest.raises(ValueError, match=r"الحالة \(status\) يجب أن تكون من نوع TaskStatus."):
        Task("task7", {"data": "value"}, "agent1", "")

def test_update_status():
    task = Task("task8", {"data": "value"})
    task.update_status(TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING

def test_update_status_invalid_status():
    task = Task("task9", {"data": "value"})
    with pytest.raises(ValueError, match=r"الحالة الجديدة \(new_status\) يجب أن تكون من نوع TaskStatus."):
        task.update_status(123)
    with pytest.raises(ValueError, match=r"الحالة الجديدة \(new_status\) يجب أن تكون من نوع TaskStatus."):
        task.update_status("")

def test_assign_agent():
    task = Task("task10", {"data": "value"})
    task.assign_agent("agent2")
    assert task.agent_id == "agent2"

def test_assign_agent_invalid_agent_id():
    task = Task("task11", {"data": "value"})
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        task.assign_agent(123)
    with pytest.raises(ValueError, match=r"معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        task.assign_agent("")

def test_to_dict():
    task = Task("task12", {"data": "value"}, "agent3", TaskStatus.COMPLETED)
    expected_dict = {
        "id": "task12",
        "payload": {"data": "value"},
        "agent_id": "agent3",
        "status": TaskStatus.COMPLETED.value
    }
    assert task.to_dict() == expected_dict

def test_from_dict():
    task_dict = {
        "id": "task13",
        "payload": {"data": "another_value"},
        "agent_id": "agent4",
        "status": TaskStatus.FAILED.value
    }
    task = Task.from_dict(task_dict)
    assert task.id == "task13"
    assert task.payload == {"data": "another_value"}
    assert task.agent_id == "agent4"
    assert task.status == TaskStatus.FAILED

def test_from_dict_default_values():
    task_dict = {
        "id": "task14",
        "payload": {"data": "default_test"}
    }
    task = Task.from_dict(task_dict)
    assert task.agent_id is None
    assert task.status == TaskStatus.PENDING

def test_repr():
    task = Task("task15", {"data": "value"}, "agent5", TaskStatus.RUNNING)
    assert repr(task) == f"Task(id=\'task15\', status=\'{TaskStatus.RUNNING.value}\', agent_id=\'agent5\')"

def test_eq():
    task1 = Task("task16", {"data": "value"}, "agent6", TaskStatus.PENDING)
    task2 = Task("task16", {"data": "value"}, "agent6", TaskStatus.PENDING)
    task3 = Task("task17", {"data": "value"}, "agent6", TaskStatus.PENDING)
    task4 = Task("task16", {"data": "different_value"}, "agent6", TaskStatus.PENDING)

    assert task1 == task2
    assert task1 != task3
    assert task1 != task4
    assert task1 != "not_a_task"

def test_hash():
    task1 = Task("task18", {"data": "value"}, "agent7", TaskStatus.PENDING)
    task2 = Task("task18", {"data": "value"}, "agent7", TaskStatus.PENDING)
    task3 = Task("task19", {"data": "value"}, "agent7", TaskStatus.PENDING)

    assert hash(task1) == hash(task2)
    assert hash(task1) != hash(task3)

def test_hash_with_nested_payload():
    payload1 = {"key1": "val1", "key2": [1, 2, {"nested": "data"}]}
    payload2 = {"key1": "val1", "key2": [1, 2, {"nested": "data"}]}
    payload3 = {"key1": "val1", "key2": [1, 2, {"nested": "different"}]}

    task1 = Task("task20", payload1, "agent8", TaskStatus.COMPLETED)
    task2 = Task("task20", payload2, "agent8", TaskStatus.COMPLETED)
    task3 = Task("task21", payload3, "agent8", TaskStatus.COMPLETED)

    assert hash(task1) == hash(task2)
    assert hash(task1) != hash(task3)

def test_hash_with_none_agent_id():
    task1 = Task("task22", {"data": "value"}, None, TaskStatus.PENDING)
    task2 = Task("task22", {"data": "value"}, None, TaskStatus.PENDING)
    assert hash(task1) == hash(task2)
