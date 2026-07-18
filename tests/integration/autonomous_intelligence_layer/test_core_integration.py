import pytest
import json
from unittest.mock import MagicMock
from enum import Enum
from unittest.mock import patch
from core.autonomous_intelligence_layer.planner_ai.planner_ai import PlannerAI
from core.autonomous_intelligence_layer.supervisor_ai.supervisor_ai import SupervisorAI
from core.autonomous_intelligence_layer.reflection_engine.reflection_engine import ReflectionEngine
from core.autonomous_intelligence_layer.memory_reasoning.memory_store import MemoryStore
from core.autonomous_intelligence_layer.knowledge_graph.knowledge_graph import KnowledgeGraph
from core.autonomous_intelligence_layer.context_manager.context_manager import ContextManager
from core.autonomous_intelligence_layer.task_graph_engine.dag import DAG
from core.autonomous_intelligence_layer.task_graph_engine.task import Task
from core.autonomous_intelligence_layer.task_graph_engine.node import Node
from core.autonomous_intelligence_layer.agent_registry.agent import Agent

@pytest.fixture
def mock_context_manager():
    cm = MagicMock(spec=ContextManager)
    cm.get_isolated_context.side_effect = lambda task_id: {}
    cm.store_isolated_context.side_effect = lambda task_id, context: None
    return cm



@pytest.fixture
def mock_agent_registry():
    ar = MagicMock()
    mock_agent_instance = Agent(agent_id="mock_agent_id", capabilities=["data_analysis"])
    mock_agent_instance.execute_task = MagicMock(return_value={"status": "COMPLETED", "result": "mocked result", "agent_id": "mock_agent_id"})
    ar.discover_agents.return_value = [mock_agent_instance]
    return ar

@pytest.fixture
def mock_execution_policies():
    ep = MagicMock()
    ep.get_policy.return_value = MagicMock(name="MockPolicy", apply=lambda x: x)
    return ep

@pytest.fixture
def mock_planner_ai():
    pa = MagicMock(spec=PlannerAI)
    pa.decompose_goal.return_value = [
        {"task_id": "task_a", "description": "Task A", "payload": {}},
        {"task_id": "task_b", "description": "Task B", "payload": {}}
    ]
    mock_dag = MagicMock(spec=DAG)
    mock_dag.id = "mock_dag_id"
    mock_task_a = Task(task_id="task_a", payload={"capabilities": ["data_analysis"]})
    mock_node_a = Node(node_id="task_a", task=mock_task_a)

    mock_task_b = Task(task_id="task_b", payload={"capabilities": ["data_analysis"]})
    mock_node_b = Node(node_id="task_b", task=mock_task_b)

    mock_dag.nodes = {"task_a": mock_node_a, "task_b": mock_node_b}
    mock_dag.topological_sort.return_value = [mock_node_a, mock_node_b]

    pa.plan_multi_step.return_value = mock_dag
    return pa

@pytest.fixture
def supervisor_ai(mock_context_manager, mock_execution_policies, mock_planner_ai, mock_agent_registry):
    return SupervisorAI(mock_context_manager, mock_execution_policies, mock_planner_ai, mock_agent_registry)

@pytest.fixture
def reflection_engine():
    return ReflectionEngine()

@pytest.fixture
def memory_store():
    return MemoryStore()

@pytest.fixture
def knowledge_graph():
    return KnowledgeGraph()

def test_planner_supervisor_integration(mock_planner_ai, supervisor_ai, mock_context_manager):
    """اختبار التكامل بين PlannerAI و SupervisorAI."""
    goal = "تحليل السوق"
    
    # 1. PlannerAI يخطط للمهمة
    decomposed_tasks = mock_planner_ai.decompose_goal(goal)
    task_dag = mock_planner_ai.plan_multi_step(decomposed_tasks)
    
    assert isinstance(task_dag, DAG)
    assert len(task_dag.nodes) > 0
    
    # 2. SupervisorAI ينفذ المهام المخطط لها
    # Mock the execute_task of agents to return a consistent result
    with patch.object(supervisor_ai.agent_registry, 'get_agent') as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.id = str("mock_agent_id")
        mock_agent.capabilities = ["data_analysis"]
        mock_agent.status = "IDLE"
        mock_agent.execute_task.return_value = {"status": "COMPLETED", "result": "mocked result for task_a", "agent_id": str(mock_agent.id)}
        mock_get_agent.return_value = mock_agent

        # Mock the context manager to simulate context updates
        mock_isolated_context = {}

        def deep_serialize(obj, seen=None):
            if seen is None:
                seen = set()
            if id(obj) in seen:
                return "<circular_reference>"
            seen.add(id(obj))
            
            if isinstance(obj, MagicMock):
                return obj.id if hasattr(obj, 'id') else str(obj)
            elif isinstance(obj, dict):
                return {k: deep_serialize(v, seen) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [deep_serialize(elem, seen) for elem in obj]
            elif isinstance(obj, Enum):
                return obj.value
            return obj

        def get_isolated_context_side_effect(task_id):
            return deep_serialize(mock_isolated_context.get(task_id, {}))

        def store_isolated_context_side_effect(task_id, context):
            mock_isolated_context[task_id] = deep_serialize(context)

        def update_isolated_context_side_effect(task_id, updates):
            if task_id not in mock_isolated_context:
                mock_isolated_context[task_id] = {}
            mock_isolated_context[task_id].update(deep_serialize(updates))

        mock_context_manager.get_isolated_context.side_effect = get_isolated_context_side_effect
        mock_context_manager.store_isolated_context.side_effect = store_isolated_context_side_effect
        mock_context_manager.update_isolated_context.side_effect = update_isolated_context_side_effect

        task_id = supervisor_ai.initialize_task(goal)
        results = supervisor_ai.execute_task(task_id)
    
    assert isinstance(results, dict)
    executed_node_ids = {item["node_id"] for item in results["results"]}

    assert all(node_id in executed_node_ids for node_id in task_dag.nodes.keys())
    assert all(item["status"] == "COMPLETED" for item in results["results"])
    # Verify that context was stored for the task
    assert task_id in mock_isolated_context
    stored_context = mock_isolated_context[task_id]
    assert stored_context["status"] == "COMPLETED"
    assert "final_results" in stored_context
    
    # Ensure no MagicMock objects are in the stored context before JSON serialization
    def convert_magicmock_to_id(obj):
        if isinstance(obj, MagicMock):
            return obj.id if hasattr(obj, 'id') else str(obj)
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
    
    json.dumps(stored_context, default=convert_magicmock_to_id) # Verify JSON serializability

def test_reflection_memory_integration(reflection_engine, memory_store):
    """اختبار التكامل بين ReflectionEngine و MemoryStore."""
    task_id = "test_task_1"
    output = {"data": "some data", "status": "success"}
    acceptance_criteria = {"status": "success"}
    
    # 1. ReflectionEngine يقوم بالتقييم
    reflection_result = reflection_engine.evaluate(task_id, str(output), "Test Objective", [str(acceptance_criteria)])
    
    assert reflection_result.score_level.value in ["excellent", "good", "acceptable", "poor"]
    assert isinstance(reflection_result.recommendations, list)
    
    from core.autonomous_intelligence_layer.memory_reasoning.memory_store import MemoryType
    # 2. MemoryStore يخزن نتيجة الانعكاس
    memory_store.store(str(reflection_result), MemoryType.WORKING, tags=[task_id, "reflection_result"])
    retrieved_memory = memory_store.search(task_id, [MemoryType.WORKING])
    
    assert len(retrieved_memory) > 0
    assert str(reflection_result) in retrieved_memory[0].content

def test_knowledge_graph_memory_integration(knowledge_graph, memory_store):
    """اختبار التكامل بين KnowledgeGraph و MemoryStore."""
    from core.autonomous_intelligence_layer.knowledge_graph.knowledge_graph import EntityType, RelationType
    # 1. إضافة بيانات إلى KnowledgeGraph
    knowledge_graph.add_entity("User", "Alice", EntityType.PERSON)
    knowledge_graph.add_entity("Task1", "Task 1", EntityType.OTHER)
    knowledge_graph.add_relationship("rel1", "User", "Task1", RelationType.OTHER)
    
    from core.autonomous_intelligence_layer.memory_reasoning.memory_store import MemoryType
    import json
    # 2. MemoryStore يخزن حالة KnowledgeGraph (أو جزء منها)
    kg_stats = knowledge_graph.get_graph_stats()
    memory_store.store(json.dumps(kg_stats), MemoryType.WORKING, tags=["global_context", "knowledge_graph_state"])
    retrieved_memory = memory_store.search(query="total_entities", memory_types=[MemoryType.WORKING])
    
    assert len(retrieved_memory) > 0
    retrieved_kg_state = json.loads(retrieved_memory[0].content)
    assert retrieved_kg_state["total_entities"] == 2
    assert retrieved_kg_state["total_relationships"] == 1

def test_full_core_workflow_integration(mock_planner_ai, supervisor_ai, reflection_engine, memory_store, knowledge_graph, mock_context_manager):
    """اختبار تدفق العمل الكامل للمكونات الأساسية للوحدة 5."""
    goal = "إنشاء تقرير شهري عن أداء المنتج"
    
    # 1. PlannerAI يخطط للمهمة
    decomposed_tasks = mock_planner_ai.decompose_goal(goal)
    task_dag = mock_planner_ai.plan_multi_step(decomposed_tasks)
    
    # 2. SupervisorAI ينفذ المهام المخطط لها
    with patch.object(supervisor_ai.agent_registry, 'get_agent') as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.id = str("mock_agent_id")
        mock_agent.capabilities = ["data_analysis"]
        mock_agent.status = "IDLE"
        mock_agent.execute_task.return_value = {"status": "COMPLETED", "result": "mocked report data for analyze_product_data", "agent_id": str(mock_agent.id)}
        mock_get_agent.return_value = mock_agent

        mock_isolated_context = {}

        def deep_serialize(obj, seen=None):
            if seen is None:
                seen = set()
            if id(obj) in seen:
                return "<circular_reference>"
            seen.add(id(obj))
            
            if isinstance(obj, MagicMock):
                return obj.id if hasattr(obj, 'id') else str(obj)
            elif isinstance(obj, dict):
                return {k: deep_serialize(v, seen) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [deep_serialize(elem, seen) for elem in obj]
            elif isinstance(obj, Enum):
                return obj.value
            return obj

        def get_isolated_context_side_effect(task_id):
            return deep_serialize(mock_isolated_context.get(task_id, {}))

        def store_isolated_context_side_effect(task_id, context):
            mock_isolated_context[task_id] = deep_serialize(context)

        def update_isolated_context_side_effect(task_id, updates):
            if task_id not in mock_isolated_context:
                mock_isolated_context[task_id] = {}
            mock_isolated_context[task_id].update(deep_serialize(updates))

        mock_context_manager.get_isolated_context.side_effect = get_isolated_context_side_effect
        mock_context_manager.store_isolated_context.side_effect = store_isolated_context_side_effect
        mock_context_manager.update_isolated_context.side_effect = update_isolated_context_side_effect

        task_id = supervisor_ai.initialize_task(goal)
        execution_results = supervisor_ai.execute_task(task_id)
    
    # 3. ReflectionEngine يقوم بالتقييم لكل مهمة
    reflection_results = {}
    for task_result in execution_results["results"]:
        task_id = task_result["node_id"]
        result = task_result["output"]
        reflection_results[task_id] = reflection_engine.evaluate(task_id, str(result), "Test Objective", ["completed"])
        assert reflection_results[task_id].score_level.value in ["excellent", "good", "acceptable", "poor"]
    
    from core.autonomous_intelligence_layer.memory_reasoning.memory_store import MemoryType
    import json
    # 4. MemoryStore يخزن نتائج التنفيذ والانعكاس
    # execution_results might contain non-serializable objects if the mock agent returns them directly
    # Convert to a serializable format if necessary, or ensure mocks return serializable data
    memory_store.store(content=goal, memory_type=MemoryType.WORKING, tags=[goal, "execution_results"], metadata=execution_results)
    # Convert ReflectionResult objects to dictionaries for JSON serialization
    serializable_reflection_results = {k: reflection_results[k].__dict__ for k in reflection_results}
    # Convert datetime objects within ReflectionResult to string
    for k in serializable_reflection_results:
        serializable_reflection_results[k]["timestamp"] = serializable_reflection_results[k]["timestamp"].isoformat()
        serializable_reflection_results[k]["score_level"] = serializable_reflection_results[k]["score_level"].value
    memory_store.store(content=goal, memory_type=MemoryType.WORKING, tags=[goal, "reflection_results"], metadata=serializable_reflection_results)
    
    retrieved_exec_mem = memory_store.search(query=goal, memory_types=[MemoryType.WORKING])
    retrieved_reflect_mem = memory_store.search(query=goal, memory_types=[MemoryType.WORKING])
    
    assert len(retrieved_exec_mem) > 0
    assert len(retrieved_reflect_mem) > 0
    
    from core.autonomous_intelligence_layer.knowledge_graph.knowledge_graph import EntityType, RelationType
    # 5. KnowledgeGraph يحدّث بناءً على النتائج
    knowledge_graph.add_entity("Report", "Monthly Product Performance", EntityType.OTHER)
    knowledge_graph.add_entity("Task", "analyze_product_data", EntityType.OTHER)
    knowledge_graph.add_relationship("rel2", "Task", "Report", RelationType.OTHER)
    
    kg_data = knowledge_graph.get_graph_stats()
    assert kg_data["total_entities"] >= 2
    assert kg_data["total_relationships"] >= 1

    # 6. تحديث السياق العام في ContextManager
    mock_context_manager.store_isolated_context("global_context", {
        "latest_report": "Monthly Product Performance",
        "kg_snapshot": knowledge_graph.get_graph_stats()
    })
    # Assert that store_isolated_context was called with serializable data
    # Assert that store_isolated_context was called with serializable data
    # We cannot use assert_called_with directly due to the nature of mock_isolated_context being updated
    # Instead, we check the content of mock_isolated_context directly.
    global_context_stored = mock_isolated_context.get("global_context")
    assert global_context_stored is not None
    assert global_context_stored["latest_report"] == "Monthly Product Performance"
    assert global_context_stored["kg_snapshot"] == deep_serialize(knowledge_graph.get_graph_stats())
    json.dumps(global_context_stored) # Verify JSON serializability


