import pytest
from core.autonomous_intelligence_layer.task_graph_engine.dag import DAG
from core.autonomous_intelligence_layer.task_graph_engine.node import Node
from core.autonomous_intelligence_layer.task_graph_engine.task import Task

@pytest.fixture
def sample_dag():
    dag = DAG()
    task_a = Task("A", {"data": "task A"})
    task_b = Task("B", {"data": "task B"})
    task_c = Task("C", {"data": "task C"})
    task_d = Task("D", {"data": "task D"})
    node_a = Node("A", task_a)
    node_b = Node("B", task_b)
    node_c = Node("C", task_c)
    node_d = Node("D", task_d)

    dag.add_node(node_a)
    dag.add_node(node_b)
    dag.add_node(node_c)
    dag.add_node(node_d)

    dag.add_edge("A", "B")
    dag.add_edge("A", "C")
    dag.add_edge("B", "D")
    dag.add_edge("C", "D")
    return dag

def test_dag_initialization():
    """اختبار تهيئة DAG."""
    dag = DAG()
    assert len(dag.nodes) == 0
    assert len(dag.adj) == 0
    assert len(dag.in_degree) == 0

def test_add_node(sample_dag):
    """اختبار إضافة عقدة إلى DAG."""
    dag = DAG()
    task_e = Task("E", {"data": "task E"})
    node_e = Node("E", task_e)
    dag.add_node(node_e)
    assert "E" in dag.nodes
    assert dag.nodes["E"] == node_e
    assert dag.in_degree["E"] == 0

    with pytest.raises(ValueError, match="العقدة ذات المعرف E موجودة بالفعل في الرسم البياني."):
        dag.add_node(node_e)

def test_add_edge(sample_dag):
    """اختبار إضافة حافة إلى DAG."""
    dag = sample_dag
    assert dag.in_degree["B"] == 1
    assert dag.in_degree["C"] == 1
    assert dag.in_degree["D"] == 2
    assert dag.adj["A"] == ["B", "C"]
    assert dag.adj["B"] == ["D"]
    assert dag.adj["C"] == ["D"]

    with pytest.raises(ValueError, match="عقدة المصدر ذات المعرف X غير موجودة."):
        dag.add_edge("X", "A")
    with pytest.raises(ValueError, match="عقدة الوجهة ذات المعرف Y غير موجودة."):
        dag.add_edge("A", "Y")

def test_add_edge_creates_cycle_raises_error():
    """اختبار أن إضافة حافة تؤدي إلى دورة ترفع خطأ."""
    dag = DAG()
    task_a = Task("A", {})
    task_b = Task("B", {})
    task_c = Task("C", {})
    node_a = Node("A", task_a)
    node_b = Node("B", task_b)
    node_c = Node("C", task_c)
    dag.add_node(node_a)
    dag.add_node(node_b)
    dag.add_node(node_c)
    dag.add_edge("A", "B")
    dag.add_edge("B", "C")
    with pytest.raises(ValueError, match="إضافة حافة من C إلى A ستنشئ دورة في الرسم البياني."):
        dag.add_edge("C", "A") # Creates a cycle

def test_has_cycle_no_cycle(sample_dag):
    """اختبار عدم وجود دورة في DAG صالح."""
    assert not sample_dag.has_cycle()

def test_topological_sort(sample_dag):
    """اختبار الفرز الطوبولوجي لـ DAG صالح."""
    sorted_nodes = sample_dag.topological_sort()
    sorted_ids = [node.id for node in sorted_nodes]
    # A -> B, A -> C, B -> D, C -> D
    # Possible valid sorts: [A, B, C, D], [A, C, B, D]
    assert sorted_ids.index("A") < sorted_ids.index("B")
    assert sorted_ids.index("A") < sorted_ids.index("C")
    assert sorted_ids.index("B") < sorted_ids.index("D")
    assert sorted_ids.index("C") < sorted_ids.index("D")
    assert len(sorted_nodes) == 4

def test_topological_sort_with_cycle_raises_error():
    """اختبار أن الفرز الطوبولوجي لـ DAG يحتوي على دورة يرفع خطأ."""
    dag = DAG()
    task_a = Task("A", {})
    task_b = Task("B", {})
    node_a = Node("A", task_a)
    node_b = Node("B", task_b)
    dag.add_node(node_a)
    dag.add_node(node_b)
    # Manually create a cycle for testing topological_sort's cycle detection
    dag.adj["A"].append("B")
    dag.in_degree["B"] += 1
    dag.adj["B"].append("A")
    dag.in_degree["A"] += 1

    assert dag.has_cycle() # Ensure the cycle is detected

    with pytest.raises(ValueError, match="لا يمكن إجراء الفرز الطوبولوجي على رسم بياني يحتوي على دورة."):
        dag.topological_sort()

def test_get_dependencies(sample_dag):
    """اختبار الحصول على تبعيات عقدة."""
    dependencies_d = sample_dag.get_dependencies("D")
    dependency_ids = {node.id for node in dependencies_d}
    assert "B" in dependency_ids
    assert "C" in dependency_ids
    assert len(dependency_ids) == 2

    dependencies_b = sample_dag.get_dependencies("B")
    dependency_ids_b = {node.id for node in dependencies_b}
    assert "A" in dependency_ids_b
    assert len(dependency_ids_b) == 1

    dependencies_a = sample_dag.get_dependencies("A")
    assert len(dependencies_a) == 0

    with pytest.raises(ValueError, match="العقدة ذات المعرف X غير موجودة."):
        sample_dag.get_dependencies("X")

def test_get_successors(sample_dag):
    """اختبار الحصول على توابع عقدة."""
    successors_a = sample_dag.get_successors("A")
    successor_ids = {node.id for node in successors_a}
    assert "B" in successor_ids
    assert "C" in successor_ids
    assert len(successor_ids) == 2

    successors_b = sample_dag.get_successors("B")
    successor_ids_b = {node.id for node in successors_b}
    assert "D" in successor_ids_b
    assert len(successor_ids_b) == 1

    successors_d = sample_dag.get_successors("D")
    assert len(successors_d) == 0

    with pytest.raises(ValueError, match="العقدة ذات المعرف X غير موجودة."):
        sample_dag.get_successors("X")

def test_dag_len(sample_dag):
    """اختبار دالة len لـ DAG."""
    assert len(sample_dag) == 4

def test_dag_contains(sample_dag):
    """اختبار دالة contains لـ DAG."""
    assert "A" in sample_dag
    assert "Z" not in sample_dag

def test_dag_repr(sample_dag):
    """اختبار تمثيل السلسلة النصية لـ DAG."""
    repr_str = repr(sample_dag)
    assert "DAG(nodes=[A, B, C, D]" in repr_str
    assert "edges=[A->B, A->C, B->D, C->D]" in repr_str

def test_add_edge_existing_edge_no_error():
    """اختبار إضافة حافة موجودة لا تسبب خطأ."""
    dag = DAG()
    task_a = Task("A", {})
    task_b = Task("B", {})
    node_a = Node("A", task_a)
    node_b = Node("B", task_b)
    dag.add_node(node_a)
    dag.add_node(node_b)
    dag.add_edge("A", "B")
    dag.add_edge("A", "B") # Add same edge again
    assert dag.adj["A"] == ["B"]
    assert dag.in_degree["B"] == 1
