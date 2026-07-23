import pytest
from unittest.mock import Mock
from src.core.autonomous_intelligence_layer.supervisor_ai.supervisor_ai import SupervisorAI


class TestSupervisorAI:
    @pytest.fixture
    def supervisor_ai(self):
        # Mock all dependencies
        mock_context_manager = Mock()
        mock_execution_policies = Mock()
        mock_planner_ai = Mock()
        mock_agent_registry = Mock()
        mock_memory_store = Mock()
        mock_knowledge_graph = Mock()
        mock_reflection_engine = Mock()
        mock_learning_engine = Mock()
        mock_error_recovery = Mock()

        return SupervisorAI(
            context_manager=mock_context_manager,
            execution_policies=mock_execution_policies,
            planner_ai=mock_planner_ai,
            agent_registry=mock_agent_registry,
            memory_store=mock_memory_store,
            knowledge_graph=mock_knowledge_graph,
            reflection_engine=mock_reflection_engine,
            learning_engine=mock_learning_engine,
            error_recovery=mock_error_recovery
        )

    def test_initialization(self, supervisor_ai):
        assert supervisor_ai is not None
        # Add more assertions for initial state if applicable

    def test_initialize_task(self, supervisor_ai):
        goal = "Test Goal"
        task_id = supervisor_ai.initialize_task(goal)
        assert task_id is not None
        supervisor_ai.context_manager.store_isolated_context.assert_called_once()
        supervisor_ai.memory_store.store.assert_called_once()
        supervisor_ai.knowledge_graph.add_entity.assert_called_once()

    def test_execute_task_success(self, supervisor_ai):
        # Mock the DAG and its methods
        mock_dag = Mock()
        mock_dag.id = "test_dag_id"
        mock_dag.topological_sort.return_value = [Mock(id="node1", task=Mock(id="subtask1", payload={}))]
        supervisor_ai._current_task_dag = mock_dag

        # Mock the agent and its execute_task method
        mock_agent = Mock()
        mock_agent.execute_task.return_value = {"status": "completed", "result": "subtask output"}
        supervisor_ai._assign_agent_for_task = Mock(return_value=mock_agent)

        task_id = "test_dag_id"
        result = supervisor_ai.execute_task(task_id)

        assert result["status"] == "COMPLETED"
        assert len(result["results"]) == 1
        assert result["results"][0]["output"] == "subtask output"
        supervisor_ai.execution_policies.get_policy.assert_called_once()
        supervisor_ai.context_manager.get_isolated_context.assert_called_once()
        supervisor_ai.context_manager.store_isolated_context.assert_called()
        supervisor_ai.knowledge_graph.add_entity.assert_called()
        supervisor_ai.knowledge_graph.add_relationship.assert_called()

    def test_execute_task_failure(self, supervisor_ai):
        mock_dag = Mock()
        mock_dag.id = "test_dag_id"
        mock_dag.topological_sort.side_effect = ValueError("DAG error")
        supervisor_ai._current_task_dag = mock_dag

        task_id = "test_dag_id"
        result = supervisor_ai.execute_task(task_id)

        assert result["status"] == "FAILED"
        assert "error" in result
        supervisor_ai.context_manager.update_isolated_context.assert_called()

    def test_get_task_status(self, supervisor_ai):
        task_id = "some_task_id"
        expected_status = {"status": "IN_PROGRESS"}
        supervisor_ai.context_manager.get_isolated_context.return_value = expected_status

        status = supervisor_ai.get_task_status(task_id)
        assert status == expected_status
        supervisor_ai.context_manager.get_isolated_context.assert_called_with(task_id)

    def test_assign_agent_for_task(self, supervisor_ai):
        mock_task = Mock()
        mock_task.payload = {"capabilities": ["test_capability"]}
        mock_agent = Mock(id="agent1")
        supervisor_ai.agent_registry.discover_agents = Mock(return_value=[mock_agent])

        assigned_agent = supervisor_ai._assign_agent_for_task(mock_task)
        assert assigned_agent == mock_agent
        supervisor_ai.agent_registry.discover_agents.assert_called_with(capabilities=["test_capability"], status="IDLE")

    def test_assign_agent_for_task_no_agent(self, supervisor_ai):
        mock_task = Mock()
        mock_task.payload = {"capabilities": ["non_existent_capability"]}
        supervisor_ai.agent_registry.discover_agents = Mock(return_value=[])

        assigned_agent = supervisor_ai._assign_agent_for_task(mock_task)
        assert assigned_agent is None
        supervisor_ai.agent_registry.discover_agents.assert_called_with(capabilities=["non_existent_capability"], status="IDLE")

    # Add more tests for other methods in SupervisorAI
