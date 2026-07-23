import pytest
from src.core.autonomous_intelligence_layer.task_graph_engine.dag import DAG
from src.core.autonomous_intelligence_layer.task_graph_engine.node import Node
from src.core.autonomous_intelligence_layer.task_graph_engine.task import Task, TaskType, TaskStatus


@pytest.fixture
def sample_dag():
    dag = DAG()
    task1 = Task(task_id="task1", payload={"description": "Process data"}, status=TaskStatus.PENDING)
    task2 = Task(task_id="task2", payload={"description": "Analyze data"}, status=TaskStatus.PENDING)
    task3 = Task(task_id="task3", payload={"description": "Report data"}, status=TaskStatus.PENDING)
    node1 = Node(node_id="node1", task=task1)
    node2 = Node(node_id="node2", task=task2)
    node3 = Node(node_id="node3", task=task3)
    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)
    return dag, node1, node2, node3


def test_dag_init():
    dag = DAG()
    assert dag.id is not None
    assert len(dag.nodes) == 0
    assert len(dag.adj) == 0
    assert len(dag.in_degree) == 0


def test_add_node(sample_dag):
    dag, node1, _, _ = sample_dag
    assert len(dag.nodes) == 3
    assert dag.nodes["node1"] == node1
    assert dag.in_degree["node1"] == 0

    with pytest.raises(ValueError, match="العقدة ذات المعرف node1 موجودة بالفعل في الرسم البياني."):
        dag.add_node(node1)

    with pytest.raises(ValueError, match="العقدة يجب أن تكون من نوع Node."):
        dag.add_node("not_a_node")


def test_add_edge(sample_dag):
    dag, node1, node2, node3 = sample_dag
    dag.add_edge("node1", "node2")
    assert dag.adj["node1"] == ["node2"]
    assert dag.in_degree["node2"] == 1

    # Test adding existing edge (should do nothing)
    dag.add_edge("node1", "node2")
    assert dag.adj["node1"] == ["node2"]
    assert dag.in_degree["node2"] == 1

    with pytest.raises(ValueError, match="عقدة المصدر ذات المعرف non_existent_node غير موجودة."):
        dag.add_edge("non_existent_node", "node1")

    with pytest.raises(ValueError, match="عقدة الوجهة ذات المعرف non_existent_node غير موجودة."):
        dag.add_edge("node1", "non_existent_node")


def test_add_edge_creates_cycle(sample_dag):
    dag, node1, node2, node3 = sample_dag
    dag.add_edge("node1", "node2")
    dag.add_edge("node2", "node3")
    with pytest.raises(ValueError, match="إضافة حافة من node3 إلى node1 ستنشئ دورة في الرسم البياني."):
        dag.add_edge("node3", "node1")


def test_get_dependencies(sample_dag):
    dag, node1, node2, node3 = sample_dag
    dag.add_edge("node1", "node2")
    dag.add_edge("node3", "node2")
    dependencies = dag.get_dependencies("node2")
    assert len(dependencies) == 2
    assert node1 in dependencies
    assert node3 in dependencies

    assert dag.get_dependencies("node1") == []

    with pytest.raises(ValueError, match="العقدة ذات المعرف non_existent_node غير موجودة."):
        dag.get_dependencies("non_existent_node")


def test_get_successors(sample_dag):
    dag, node1, node2, node3 = sample_dag
    dag.add_edge("node1", "node2")
    dag.add_edge("node1", "node3")
    successors = dag.get_successors("node1")
    assert len(successors) == 2
    assert node2 in successors
    assert node3 in successors

    assert dag.get_successors("node2") == []

    with pytest.raises(ValueError, match="العقدة ذات المعرف non_existent_node غير موجودة."):
        dag.get_successors("non_existent_node")


def test_has_cycle(sample_dag):
    dag, node1, node2, node3 = sample_dag
    assert not dag.has_cycle()

    dag.add_edge("node1", "node2")
    dag.add_edge("node2", "node3")
    assert not dag.has_cycle()

    # Manually create a cycle for testing has_cycle
    dag.adj["node3"].append("node1")
    dag.in_degree["node1"] += 1
    assert dag.has_cycle()


def test_topological_sort(sample_dag):
    dag, node1, node2, node3 = sample_dag
    dag.add_edge("node1", "node2")
    dag.add_edge("node1", "node3")
    dag.add_edge("node2", "node3")

    sorted_nodes = dag.topological_sort()
    assert len(sorted_nodes) == 3
    # node1 must be first
    assert sorted_nodes[0] == node1
    # node2 and node3 can be in any order after node1, but node2 must be before node3 if node1->node2->node3
    # Given node1->node2, node1->node3, node2->node3, valid sorts are [node1, node2, node3]
    # The specific order depends on the deque behavior, but node1 must come first.
    # Let's check dependencies for a more robust assertion
    node_ids = [node.id for node in sorted_nodes]
    assert node_ids.index("node1") < node_ids.index("node2")
    assert node_ids.index("node1") < node_ids.index("node3")
    assert node_ids.index("node2") < node_ids.index("node3")

    # Test with a cycle
    dag_with_cycle = DAG()
    task_a = Task(task_id="a", payload={"description": "A"}, status=TaskStatus.PENDING)
    task_b = Task(task_id="b", payload={"description": "B"}, status=TaskStatus.PENDING)
    node_a = Node(node_id="a", task=task_a)
    node_b = Node(node_id="b", task=task_b)
    dag_with_cycle.add_node(node_a)
    dag_with_cycle.add_node(node_b)
    # Manually create a cycle for topological_sort test
    dag_with_cycle.adj["a"].append("b")
    dag_with_cycle.in_degree["b"] += 1
    dag_with_cycle.adj["b"].append("a")
    dag_with_cycle.in_degree["a"] += 1
    with pytest.raises(ValueError, match="لا يمكن إجراء الفرز الطوبولوجي على رسم بياني يحتوي على دورة."):
        dag_with_cycle.topological_sort()


def test_len(sample_dag):
    dag, _, _, _ = sample_dag
    assert len(dag) == 3


def test_contains(sample_dag):
    dag, _, _, _ = sample_dag
    assert "node1" in dag
    assert "non_existent_node" not in dag


def test_repr(sample_dag):
    dag, _, _, _ = sample_dag
    assert repr(dag) == f"DAG(id='{dag.id}', nodes_count=3)"
