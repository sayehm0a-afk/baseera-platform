import pytest
from core.autonomous_intelligence_layer.task_graph_engine.node import Node
from core.autonomous_intelligence_layer.task_graph_engine.task import Task

def test_node_initialization():
    """اختبار تهيئة العقدة الأساسية."""
    task = Task(task_id="task1", payload={"data": "value"})
    node = Node(node_id="node1", task=task)
    assert node.id == "node1"
    assert node.task == task

def test_node_id_validation():
    """اختبار التحقق من صحة معرف العقدة."""
    task = Task(task_id="task1", payload={})
    with pytest.raises(ValueError, match="معرف العقدة \(node_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Node(node_id="", task=task)
    with pytest.raises(ValueError, match="معرف العقدة \(node_id\) يجب أن يكون سلسلة نصية غير فارغة."):
        Node(node_id=None, task=task)

def test_task_validation():
    """اختبار التحقق من صحة كائن المهمة."""
    with pytest.raises(ValueError, match="المهمة \(task\) يجب أن تكون من نوع Task."):
        Node(node_id="node1", task="invalid_task")
    with pytest.raises(ValueError, match="المهمة \(task\) يجب أن تكون من نوع Task."):
        Node(node_id="node1", task=None)

def test_node_to_dict():
    """اختبار تحويل العقدة إلى قاموس."""
    task = Task(task_id="task2", payload={"key": 123}, agent_id="agentX", status="RUNNING")
    node = Node(node_id="node2", task=task)
    expected_dict = {
        "id": "node2",
        "task": {
            "id": "task2",
            "payload": {"key": 123},
            "agent_id": "agentX",
            "status": "RUNNING"
        }
    }
    assert node.to_dict() == expected_dict

def test_node_from_dict():
    """اختبار إنشاء عقدة من قاموس."""
    task_dict = {
        "id": "task3",
        "payload": {"another_key": "another_value"},
        "agent_id": "agentY",
        "status": "COMPLETED"
    }
    node_dict = {
        "id": "node3",
        "task": task_dict
    }
    node = Node.from_dict(node_dict)
    assert node.id == "node3"
    assert node.task.id == "task3"
    assert node.task.payload == {"another_key": "another_value"}
    assert node.task.agent_id == "agentY"
    assert node.task.status == "COMPLETED"

def test_node_equality():
    """اختبار تساوي كائنين من نوع Node."""
    task1 = Task(task_id="task4", payload={"a": 1})
    task2 = Task(task_id="task5", payload={"b": 2})
    node1 = Node(node_id="node4", task=task1)
    node2 = Node(node_id="node4", task=task1)
    node3 = Node(node_id="node5", task=task2)
    assert node1 == node2
    assert node1 != node3

def test_node_hashable():
    """اختبار أن كائن Node قابل للتجزئة (hashable)."""
    task = Task(task_id="task6", payload={"c": 3})
    node1 = Node(node_id="node6", task=task)
    node2 = Node(node_id="node6", task=task)
    node_set = {node1}
    assert node2 in node_set

def test_node_repr():
    """اختبار تمثيل السلسلة النصية لكائن Node."""
    task = Task(task_id="task7", payload={}, status="NEW")
    node = Node(node_id="node7", task=task)
    assert repr(node) == "Node(id=\'node7\', task=Task(id=\'task7\', status=\'NEW\', agent_id=\'None\'))"
