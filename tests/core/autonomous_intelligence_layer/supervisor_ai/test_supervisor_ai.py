import pytest
from unittest.mock import Mock, MagicMock
from core.autonomous_intelligence_layer.supervisor_ai.supervisor_ai import SupervisorAI
from core.autonomous_intelligence_layer.context_manager.context_manager import ContextManager
from core.autonomous_intelligence_layer.execution_policies.execution_policies import ExecutionPolicies
from core.autonomous_intelligence_layer.planner_ai.planner_ai import PlannerAI
from core.autonomous_intelligence_layer.agent_registry.agent_registry import AgentRegistry
from core.autonomous_intelligence_layer.agent_registry.agent import Agent
from core.autonomous_intelligence_layer.task_graph_engine.dag import DAG
from core.autonomous_intelligence_layer.task_graph_engine.node import Node
from core.autonomous_intelligence_layer.task_graph_engine.task import Task

@pytest.fixture
def mock_context_manager():
    cm = MagicMock(spec=ContextManager)
    cm.get_isolated_context.return_value = {}
    cm.store_isolated_context.return_value = None
    cm.update_isolated_context.return_value = None
    return cm

@pytest.fixture
def mock_execution_policies():
    ep = MagicMock(spec=ExecutionPolicies)
    mock_policy = Mock()
    mock_policy.apply.side_effect = lambda ctx: {**ctx, "policy_applied": True}
    ep.get_policy.return_value = mock_policy
    return ep

@pytest.fixture
def mock_planner_ai():
    pa = MagicMock(spec=PlannerAI)
    # Mock decompose_goal
    pa.decompose_goal.return_value = [
        {"task_id": "task1", "description": "Desc1", "payload": {"capabilities": ["cap1"]}},
        {"task_id": "task2", "description": "Desc2", "payload": {"capabilities": ["cap2"]}}
    ]
    # Mock plan_multi_step
    mock_dag = DAG()
    mock_dag.id = "mock_dag_id" # إضافة خاصية id
    task1 = Task("task1", {"capabilities": ["cap1"]})
    task2 = Task("task2", {"capabilities": ["cap2"]})
    mock_dag.add_node(Node("task1", task1))
    mock_dag.add_node(Node("task2", task2))
    mock_dag.add_edge("task1", "task2")
    pa.plan_multi_step.return_value = mock_dag
    return pa

@pytest.fixture
def mock_agent_registry():
    ar = MagicMock(spec=AgentRegistry)
    agent1 = MagicMock(spec=Agent, id="agent_A", capabilities=["cap1"], status="IDLE")
    agent2 = MagicMock(spec=Agent, id="agent_B", capabilities=["cap2"], status="IDLE")
    ar.discover_agents.side_effect = lambda capabilities, status: [
        agent1 if "cap1" in capabilities and status == "IDLE" else None,
        agent2 if "cap2" in capabilities and status == "IDLE" else None
    ]
    ar.discover_agents.return_value = [agent1, agent2] # Default for general discovery
    ar.get_agent.side_effect = lambda agent_id: {"agent_A": agent1, "agent_B": agent2}.get(agent_id)
    return ar

@pytest.fixture
def supervisor_ai(mock_context_manager, mock_execution_policies, mock_planner_ai, mock_agent_registry):
    return SupervisorAI(
        context_manager=mock_context_manager,
        execution_policies=mock_execution_policies,
        planner_ai=mock_planner_ai,
        agent_registry=mock_agent_registry
    )

def test_supervisor_ai_initialization(supervisor_ai, mock_context_manager, mock_execution_policies, mock_planner_ai, mock_agent_registry):
    """اختبار تهيئة SupervisorAI."""
    assert supervisor_ai.context_manager == mock_context_manager
    assert supervisor_ai.execution_policies == mock_execution_policies
    assert supervisor_ai.planner_ai == mock_planner_ai
    assert supervisor_ai.agent_registry == mock_agent_registry
    assert supervisor_ai._current_task_dag is None

def test_initialize_task(supervisor_ai, mock_context_manager, mock_planner_ai):
    """اختبار تهيئة مهمة جديدة."""
    goal = "تحليل السوق"
    initial_context = {"user_id": "123"}
    task_id = supervisor_ai.initialize_task(goal, initial_context)

    mock_planner_ai.decompose_goal.assert_called_once_with(goal)
    mock_planner_ai.plan_multi_step.assert_called_once()
    mock_context_manager.store_isolated_context.assert_called_once()
    stored_context = mock_context_manager.store_isolated_context.call_args[0][1]
    assert stored_context["goal"] == goal
    assert stored_context["status"] == "INITIALIZED"
    assert stored_context["user_id"] == "123"
    assert supervisor_ai._current_task_dag is not None
    assert task_id == supervisor_ai._current_task_dag.id

def test_execute_task(supervisor_ai, mock_context_manager, mock_execution_policies, mock_planner_ai, mock_agent_registry):
    """اختبار تنفيذ مهمة."""
    goal = "تحليل السوق"
    task_id = supervisor_ai.initialize_task(goal)
    
    # إعداد السياق الذي سيتم استرداده بواسطة execute_task
    mock_context_manager.get_isolated_context.return_value = {"goal": goal, "status": "INITIALIZED"}

    # إعداد الوكلاء لـ _assign_agent_for_task
    agent_cap1 = MagicMock(spec=Agent, id="agent_cap1", capabilities=["cap1"], status="IDLE")
    agent_cap2 = MagicMock(spec=Agent, id="agent_cap2", capabilities=["cap2"], status="IDLE")
    mock_agent_registry.discover_agents.side_effect = [
        [agent_cap1], # للمهمة task1
        [agent_cap2]  # للمهمة task2
    ]

    results = supervisor_ai.execute_task(task_id, "FastMode")

    mock_context_manager.get_isolated_context.assert_called_with(task_id)
    mock_execution_policies.get_policy.assert_called_once_with("FastMode")
    mock_execution_policies.get_policy.return_value.apply.assert_called_once()
    assert results["status"] == "COMPLETED"
    assert len(results["results"]) == 2
    assert results["results"][0]["node_id"] == "task1"
    assert results["results"][1]["node_id"] == "task2"
    assert mock_agent_registry.discover_agents.call_count == 2
    assert agent_cap1.update_status.call_count == 2 # RUNNING then IDLE
    assert agent_cap2.update_status.call_count == 2 # RUNNING then IDLE
    assert mock_context_manager.update_isolated_context.call_count >= 4 # تحديثات الحالة للوكلاء والمهام

def test_execute_task_no_dag(supervisor_ai):
    """اختبار تنفيذ مهمة بدون DAG مهيأ يرفع خطأ."""
    with pytest.raises(ValueError, match=f"لم يتم العثور على DAG للمهمة non_existent_task. يرجى تهيئة المهمة أولاً."):
        supervisor_ai.execute_task("non_existent_task")

def test_get_task_status(supervisor_ai, mock_context_manager):
    """اختبار استرداد حالة المهمة."""
    task_id = "test_task_id"
    expected_status = {"status": "RUNNING", "progress": 0.5}
    mock_context_manager.get_isolated_context.return_value = expected_status
    status = supervisor_ai.get_task_status(task_id)
    mock_context_manager.get_isolated_context.assert_called_once_with(task_id)
    assert status == expected_status

def test_supervisor_ai_repr(supervisor_ai):
    """اختبار تمثيل السلسلة النصية لـ SupervisorAI."""
    assert repr(supervisor_ai) == "SupervisorAI()"
