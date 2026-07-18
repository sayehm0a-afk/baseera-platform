import pytest
from core.autonomous_intelligence_layer.planner_ai.planner_ai import PlannerAI
from core.autonomous_intelligence_layer.task_graph_engine.dag import DAG
from core.autonomous_intelligence_layer.task_graph_engine.node import Node
from core.autonomous_intelligence_layer.task_graph_engine.task import Task

def test_planner_ai_initialization():
    """اختبار تهيئة PlannerAI."""
    planner = PlannerAI()
    assert isinstance(planner.task_graph_engine, DAG)
    assert len(planner.task_graph_engine.nodes) == 0

def test_decompose_goal_market_analysis():
    """اختبار تفكيك هدف 'تحليل السوق'."""
    planner = PlannerAI()
    goal = "تحليل السوق"
    decomposed_tasks = planner.decompose_goal(goal)
    assert len(decomposed_tasks) == 3
    assert decomposed_tasks[0]["task_id"] == "collect_market_data"
    assert decomposed_tasks[1]["task_id"] == "process_market_data"
    assert decomposed_tasks[2]["task_id"] == "analyze_market_trends"

def test_decompose_goal_generic():
    """اختبار تفكيك هدف عام."""
    planner = PlannerAI()
    goal = "مهمة عامة"
    decomposed_tasks = planner.decompose_goal(goal)
    assert len(decomposed_tasks) == 1
    assert decomposed_tasks[0]["task_id"] == "generic_task_1"
    assert decomposed_tasks[0]["description"] == f"مهمة عامة لتنفيذ {goal}"

def test_plan_multi_step():
    """اختبار التخطيط متعدد الخطوات وإنشاء DAG."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {"step": 1}},
        {"task_id": "T2", "payload": {"step": 2}},
        {"task_id": "T3", "payload": {"step": 3}}
    ]
    dag = planner.plan_multi_step(decomposed_tasks)
    assert isinstance(dag, DAG)
    assert len(dag.nodes) == 3
    assert "T1" in dag.nodes
    assert "T2" in dag.nodes
    assert "T3" in dag.nodes
    assert dag.adj["T1"] == ["T2"]
    assert dag.adj["T2"] == ["T3"]
    assert not dag.has_cycle()
    assert planner.task_graph_engine == dag

def test_create_dependency_graph():
    """اختبار إنشاء رسم بياني للتبعيات."""
    planner = PlannerAI()
    tasks_with_dependencies = [
        {"task_id": "Start", "payload": {}},
        {"task_id": "ProcessA", "payload": {}, "dependencies": ["Start"]},
        {"task_id": "ProcessB", "payload": {}, "dependencies": ["Start"]},
        {"task_id": "End", "payload": {}, "dependencies": ["ProcessA", "ProcessB"]}
    ]
    dag = planner.create_dependency_graph(tasks_with_dependencies)
    assert isinstance(dag, DAG)
    assert len(dag.nodes) == 4
    assert dag.adj["Start"] == ["ProcessA", "ProcessB"]
    assert dag.adj["ProcessA"] == ["End"]
    assert dag.adj["ProcessB"] == ["End"]
    assert not dag.has_cycle()
    assert planner.task_graph_engine == dag

def test_plan_parallel_execution():
    """اختبار تخطيط التنفيذ المتوازي."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {}},
        {"task_id": "T2", "payload": {}},
        {"task_id": "T3", "payload": {}}
    ]
    dag = planner.plan_multi_step(decomposed_tasks)
    parallel_plan = planner.plan_parallel_execution(dag)
    assert isinstance(parallel_plan, list)
    assert len(parallel_plan) == 3 # في هذا التنفيذ الوهمي، كل مهمة في مستوى خاص بها
    assert all(isinstance(level, list) for level in parallel_plan)
    assert all(isinstance(node, Node) for level in parallel_plan for node in level)

def test_plan_sequential_execution():
    """اختبار تخطيط التنفيذ المتسلسل."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {}},
        {"task_id": "T2", "payload": {}},
        {"task_id": "T3", "payload": {}}
    ]
    dag = planner.plan_multi_step(decomposed_tasks)
    sequential_plan = planner.plan_sequential_execution(dag)
    assert isinstance(sequential_plan, list)
    assert len(sequential_plan) == 3
    assert [node.id for node in sequential_plan] == ["T1", "T2", "T3"]

def test_plan_conditional_execution():
    """اختبار تخطيط التنفيذ الشرطي."""
    planner = PlannerAI()
    tasks_with_dependencies = [
        {"task_id": "A", "payload": {}},
        {"task_id": "B", "payload": {}, "dependencies": ["A"]},
        {"task_id": "C", "payload": {}, "dependencies": ["A"]}
    ]
    original_dag = planner.create_dependency_graph(tasks_with_dependencies)
    
    condition_map = {"B": False} # لا تنفذ B
    conditional_dag = planner.plan_conditional_execution(original_dag, condition_map)
    
    assert "A" in conditional_dag.nodes
    assert "B" not in conditional_dag.nodes
    assert "C" in conditional_dag.nodes
    assert conditional_dag.adj["A"] == ["C"] # A يجب أن تشير فقط إلى C الآن

def test_plan_recursive():
    """اختبار التخطيط المتكرر."""
    planner = PlannerAI()
    goal = "تحليل السوق"
    recursive_dag = planner.plan_recursive(goal, max_depth=2)
    assert isinstance(recursive_dag, DAG)
    assert len(recursive_dag.nodes) > 0
    # في هذا التنفيذ الوهمي، التخطيط المتكرر هو نفسه التخطيط متعدد الخطوات بعد التفكيك الأولي
    decomposed = planner.decompose_goal(goal)
    expected_dag = planner.plan_multi_step(decomposed)
    assert len(recursive_dag.nodes) == len(expected_dag.nodes)

def test_replan_dynamically():
    """اختبار إعادة التخطيط ديناميكيًا."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {}},
        {"task_id": "T2", "payload": {}},
        {"task_id": "T3", "payload": {}}
    ]
    original_dag = planner.plan_multi_step(decomposed_tasks)
    
    replanned_dag = planner.replan_dynamically(original_dag, "T2", {"error": "network_issue"})
    assert isinstance(replanned_dag, DAG)
    assert "T2" not in replanned_dag.nodes # المهمة الفاشلة يجب أن تُزال أو يُعاد التخطيط لها
    assert "T1" in replanned_dag.nodes
    assert "T3" in replanned_dag.nodes
    assert len(replanned_dag.nodes) == 2
    assert replanned_dag.adj["T1"] == ["T3"]

def test_optimize_plan():
    """اختبار تحسين الخطة."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {}},
        {"task_id": "T2", "payload": {}}
    ]
    original_dag = planner.plan_multi_step(decomposed_tasks)
    optimized_dag = planner.optimize_plan(original_dag, {"cost": "minimize"})
    assert optimized_dag == original_dag # في هذا التنفيذ الوهمي، لا يوجد تغيير فعلي

def test_estimate_cost():
    """اختبار تقدير التكلفة."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {}},
        {"task_id": "T2", "payload": {}},
        {"task_id": "T3", "payload": {}}
    ]
    dag = planner.plan_multi_step(decomposed_tasks)
    cost_estimate = planner.estimate_cost(dag)
    assert "total_cost" in cost_estimate
    assert "estimated_time" in cost_estimate
    assert cost_estimate["total_cost"] == 3 * 10.0 # 3 مهام * 10.0 لكل مهمة
    assert cost_estimate["estimated_time"] == "1.5h"

def test_planner_ai_repr():
    """اختبار تمثيل السلسلة النصية لـ PlannerAI."""
    planner = PlannerAI()
    decomposed_tasks = [
        {"task_id": "T1", "payload": {}},
        {"task_id": "T2", "payload": {}}
    ]
    planner.plan_multi_step(decomposed_tasks)
    repr_str = repr(planner)
    assert "PlannerAI(current_dag_nodes=2)" in repr_str
