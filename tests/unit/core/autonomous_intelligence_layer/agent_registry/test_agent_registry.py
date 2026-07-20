import pytest
from src.core.autonomous_intelligence_layer.agent_registry.agent_registry import AgentRegistry
from src.core.autonomous_intelligence_layer.agent_registry.agent import Agent

class TestAgentRegistry:
    @pytest.fixture
    def registry(self):
        return AgentRegistry()

    def test_initialization(self, registry):
        assert registry is not None
        assert len(registry._agents) == 0

    def test_register_agent(self, registry):
        agent = Agent(agent_id="agent1", capabilities=["search", "write"])
        registry.register_agent(agent)
        assert len(registry._agents) == 1
        assert "agent1" in registry._agents

    def test_register_duplicate_agent(self, registry):
        agent1 = Agent(agent_id="agent1", capabilities=["search"])
        agent2 = Agent(agent_id="agent1", capabilities=["write"])
        registry.register_agent(agent1)
        with pytest.raises(ValueError):
            registry.register_agent(agent2)

    def test_get_agent(self, registry):
        agent = Agent(agent_id="agent1", capabilities=["search"])
        registry.register_agent(agent)
        retrieved_agent = registry.get_agent("agent1")
        assert retrieved_agent == agent

    def test_get_nonexistent_agent(self, registry):
        with pytest.raises(ValueError):
            registry.get_agent("nonexistent")

    def test_unregister_agent(self, registry):
        agent = Agent(agent_id="agent1", capabilities=["search"])
        registry.register_agent(agent)
        registry.unregister_agent("agent1")
        assert len(registry._agents) == 0

    def test_unregister_nonexistent_agent(self, registry):
        with pytest.raises(ValueError):
            registry.unregister_agent("nonexistent")

    def test_find_agents_by_capability(self, registry):
        agent1 = Agent(agent_id="agent1", capabilities=["search", "write"])
        agent2 = Agent(agent_id="agent2", capabilities=["search"])
        agent3 = Agent(agent_id="agent3", capabilities=["code"])
        registry.register_agent(agent1)
        registry.register_agent(agent2)
        registry.register_agent(agent3)

        search_agents = registry.discover_agents(capabilities=["search"])
        assert len(search_agents) == 2
        assert agent1 in search_agents
        assert agent2 in search_agents

        code_agents = registry.discover_agents(capabilities=["code"])
        assert len(code_agents) == 1
        assert agent3 in code_agents

        unknown_agents = registry.discover_agents(capabilities=["unknown"])
        assert len(unknown_agents) == 0

    def test_get_all_agents(self, registry):
        agent1 = Agent(agent_id="agent1", capabilities=["search"])
        agent2 = Agent(agent_id="agent2", capabilities=["write"])
        registry.register_agent(agent1)
        registry.register_agent(agent2)

        all_agents = list(registry._agents.values())
        assert len(all_agents) == 2
        assert agent1 in all_agents
        assert agent2 in all_agents

    def test_register_agent_invalid_type(self, registry):
        with pytest.raises(ValueError, match="الوكيل يجب أن يكون من نوع Agent."):
            registry.register_agent("not_an_agent")

    def test_unregister_agent_invalid_id(self, registry):
        with pytest.raises(ValueError, match="معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
            registry.unregister_agent("")

    def test_get_agent_invalid_id(self, registry):
        with pytest.raises(ValueError, match="معرف الوكيل \(agent_id\) يجب أن يكون سلسلة نصية غير فارغة."):
            registry.get_agent("")

    def test_discover_agents_by_status(self, registry):
        agent1 = Agent(agent_id="agent1", capabilities=["search"], status="ACTIVE")
        agent2 = Agent(agent_id="agent2", capabilities=["write"], status="IDLE")
        registry.register_agent(agent1)
        registry.register_agent(agent2)

        active_agents = registry.discover_agents(status="ACTIVE")
        assert len(active_agents) == 1
        assert agent1 in active_agents

    def test_discover_agents_by_capability_and_status(self, registry):
        agent1 = Agent(agent_id="agent1", capabilities=["search"], status="ACTIVE")
        agent2 = Agent(agent_id="agent2", capabilities=["search"], status="IDLE")
        registry.register_agent(agent1)
        registry.register_agent(agent2)

        agents = registry.discover_agents(capabilities=["search"], status="ACTIVE")
        assert len(agents) == 1
        assert agent1 in agents

    def test_update_agent_status(self, registry):
        agent = Agent(agent_id="agent1", capabilities=["search"])
        registry.register_agent(agent)
        registry.update_agent_status("agent1", "BUSY")
        assert registry.get_agent("agent1").status == "BUSY"

    def test_len(self, registry):
        assert len(registry) == 0
        registry.register_agent(Agent(agent_id="agent1", capabilities=["search"]))
        assert len(registry) == 1

    def test_contains(self, registry):
        registry.register_agent(Agent(agent_id="agent1", capabilities=["search"]))
        assert "agent1" in registry
        assert "agent2" not in registry

    def test_repr(self, registry):
        assert repr(registry) == "AgentRegistry(registered_agents=0)"
        registry.register_agent(Agent(agent_id="agent1", capabilities=["search"]))
        assert repr(registry) == "AgentRegistry(registered_agents=1)"
