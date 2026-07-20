import pytest
from unittest.mock import Mock, AsyncMock
from src.core.autonomous_intelligence_layer.reflection_engine.reflection_engine import ReflectionEngine, ReflectionPolicy
from src.core.autonomous_intelligence_layer.memory_reasoning.memory_store import MemoryStore, MemoryType
from src.core.autonomous_intelligence_layer.knowledge_graph.knowledge_graph import KnowledgeGraph
from src.core.llm_abstraction.base_llm_client import BaseLLMClient
from src.core.autonomous_intelligence_layer.knowledge_graph.knowledge_graph import EntityType, RelationType

class TestReflectionEngine:
    @pytest.fixture
    def mock_llm_client(self):
        mock = Mock(spec=BaseLLMClient)
        mock.generate_text = AsyncMock(return_value="Mocked reflection output")
        return mock

    @pytest.fixture
    def mock_memory_store(self):
        mock = Mock(spec=MemoryStore)
        mock.retrieve_memories = Mock(return_value=[])
        mock.add_memory = Mock()
        mock.summarize_memories = Mock(return_value="Mocked summary")
        return mock

    @pytest.fixture
    def mock_knowledge_graph(self):
        mock = Mock(spec=KnowledgeGraph)
        mock.query_entity = Mock(return_value=None)
        mock.add_entity = Mock()
        mock.add_relationship = Mock()
        return mock

    @pytest.fixture
    def reflection_engine(self, mock_llm_client, mock_memory_store, mock_knowledge_graph):
        return ReflectionEngine(
            llm_client=mock_llm_client,
            memory_store=mock_memory_store,
            knowledge_graph=mock_knowledge_graph
        )

    def test_initialization(self, reflection_engine):
        assert reflection_engine.llm_client is not None
        assert reflection_engine.memory_store is not None
        assert reflection_engine.knowledge_graph is not None
        assert isinstance(reflection_engine.policy, ReflectionPolicy)

    @pytest.mark.asyncio
    async def test_reflect_on_memories(self, reflection_engine, mock_llm_client, mock_memory_store):
        mock_memory_store.retrieve_memories.return_value = [
            Mock(content="memory 1", memory_type=MemoryType.EPISODIC),
            Mock(content="memory 2", memory_type=MemoryType.EPISODIC)
        ]
        reflection_text = await reflection_engine.reflect_on_memories("test_agent", "initial_goal")
        assert reflection_text == "Mocked reflection output"
        mock_llm_client.generate_text.assert_called_once()
        mock_memory_store.store.assert_called_once_with(
            content="Mocked reflection output",
            memory_type=MemoryType.REFLECTION,
            source="test_agent",
            metadata={"source_goal": "initial_goal"},
        )

    @pytest.mark.asyncio
    async def test_reflect_on_memories_no_memories(self, reflection_engine, mock_llm_client, mock_memory_store):
        mock_memory_store.retrieve_memories.return_value = []
        reflection_text = await reflection_engine.reflect_on_memories("test_agent", "initial_goal")
        assert reflection_text is None
        mock_llm_client.generate_text.assert_not_called()
        mock_memory_store.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_knowledge_graph_from_reflection(self, reflection_engine, mock_knowledge_graph):
        reflection_data = {
            "entities": [
                {"entity_id": "ent1", "name": "Entity 1", "entity_type": "CONCEPT"}
            ],
            "relationships": [
                {"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "RELATED_TO"}
            ]
        }
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine.update_knowledge_graph_from_reflection(reflection_data)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.CONCEPT,
            attributes={}
        )
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.RELATED_TO,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_update_knowledge_graph_from_reflection_no_data(self, reflection_engine, mock_knowledge_graph):
        reflection_data = {"entities": [], "relationships": []}
        await reflection_engine.update_knowledge_graph_from_reflection(reflection_data)
        mock_knowledge_graph.add_entity.assert_not_called()
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_perform_reflection_cycle(self, reflection_engine, mock_llm_client, mock_memory_store, mock_knowledge_graph):
        mock_memory_store.retrieve_memories.return_value = [
            Mock(content="memory 1", memory_type=MemoryType.EPISODIC),
            Mock(content="memory 2", memory_type=MemoryType.EPISODIC)
        ]
        mock_llm_client.generate_text.return_value = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "CONCEPT"}], "relationships": []}'
        await reflection_engine.perform_reflection_cycle("test_agent", "initial_goal")
        assert mock_llm_client.generate_text.call_count == 1
        mock_memory_store.store.assert_called_once()
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.CONCEPT,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_perform_reflection_cycle_no_reflection_data(self, reflection_engine, mock_llm_client, mock_memory_store, mock_knowledge_graph):
        mock_memory_store.retrieve_memories.return_value = [
            Mock(content="memory 1", memory_type=MemoryType.EPISODIC)
        ]
        mock_llm_client.generate_text.side_effect = [
            "Reflection output",
            "Invalid JSON"
        ]
        await reflection_engine.perform_reflection_cycle("test_agent", "initial_goal")
        assert mock_llm_client.generate_text.call_count == 1
        mock_memory_store.store.assert_called_once()
        mock_knowledge_graph.add_entity.assert_not_called()
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_perform_reflection_cycle_no_memories(self, reflection_engine, mock_llm_client, mock_memory_store, mock_knowledge_graph):
        mock_memory_store.retrieve_memories.return_value = []
        await reflection_engine.perform_reflection_cycle("test_agent", "initial_goal")
        mock_llm_client.generate_text.assert_not_called()
        mock_memory_store.store.assert_not_called()
        mock_knowledge_graph.add_entity.assert_not_called()
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_reflection_prompt(self, reflection_engine, mock_memory_store):
        mock_memory_store.summarize_memories.return_value = "Summary of recent events."
        prompt = reflection_engine._generate_reflection_prompt("test_agent", "initial_goal")
        assert "Summary of recent events." in prompt
        assert "test_agent" in prompt
        assert "initial_goal" in prompt

    @pytest.mark.asyncio
    async def test_extract_knowledge_from_reflection(self, reflection_engine):
        reflection_text = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "CONCEPT"}], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "RELATED_TO"}]}'
        knowledge = await reflection_engine._extract_knowledge_from_reflection(reflection_text)
        assert "entities" in knowledge
        assert len(knowledge["entities"]) == 1
        assert knowledge["entities"][0]["entity_id"] == "ent1"
        assert "relationships" in knowledge
        assert len(knowledge["relationships"]) == 1
        assert knowledge["relationships"][0]["relationship_id"] == "rel1"

    @pytest.mark.asyncio
    async def test_extract_knowledge_from_reflection_invalid_json(self, reflection_engine):
        reflection_text = "Invalid JSON string"
        knowledge = await reflection_engine._extract_knowledge_from_reflection(reflection_text)
        assert knowledge == {"entities": [], "relationships": []}

    @pytest.mark.asyncio
    async def test_extract_knowledge_from_reflection_missing_keys(self, reflection_engine):
        reflection_text = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "CONCEPT"}]}'
        knowledge = await reflection_engine._extract_knowledge_from_reflection(reflection_text)
        assert "entities" in knowledge
        assert len(knowledge["entities"]) == 1
        assert "relationships" in knowledge
        assert len(knowledge["relationships"]) == 0

    @pytest.mark.asyncio
    async def test_process_reflection_output(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "CONCEPT"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.CONCEPT,
            attributes={}
        )
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_invalid_json(self, reflection_engine, mock_knowledge_graph):
        reflection_output = "Invalid JSON"
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_no_entities_or_relationships(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_entity_type_conversion(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "COMPANY"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.COMPANY,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_relationship_type_conversion(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "OWNS"}]}'
        # Mock add_entity calls to ensure entities exist for relationship creation
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.OWNS,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_entity_type_invalid(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "INVALID_TYPE"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_relationship_type_invalid(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "INVALID_TYPE"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_entity_for_relationship(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "non_existent_ent", "target_entity_id": "ent2", "relationship_type": "RELATED_TO"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_relationship_with_attributes(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "RELATED_TO", "attributes": {"weight": 0.5}}]}'
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.RELATED_TO,
            attributes={"weight": 0.5}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_entity_with_attributes(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "PERSON", "attributes": {"age": 30}}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.PERSON,
            attributes={"age": 30}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_multiple_entities_relationships(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "PERSON"}, {"entity_id": "ent2", "name": "Entity 2", "entity_type": "COMPANY"}], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "WORKS_FOR"}]}'
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_any_call(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.PERSON,
            attributes={}
        )
        mock_knowledge_graph.add_entity.assert_any_call(
            entity_id="ent2",
            name="Entity 2",
            entity_type=EntityType.COMPANY,
            attributes={}
        )
        assert mock_knowledge_graph.add_entity.call_count == 2
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.WORKS_FOR,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_empty_input(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_only_entities(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "PERSON"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.PERSON,
            attributes={}
        )
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_only_relationships(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "RELATED_TO"}]}'
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.RELATED_TO,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_entity_id(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"name": "Entity 1", "entity_type": "PERSON"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_relationship_id(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "RELATED_TO"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_source_entity_id(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "target_entity_id": "ent2", "relationship_type": "RELATED_TO"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_target_entity_id(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "relationship_type": "RELATED_TO"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_relationship_type(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_entity_name(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "entity_type": "PERSON"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_missing_entity_type(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_entity_type_case_insensitive(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "person"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.PERSON,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_relationship_type_case_insensitive(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "related_to"}]}'
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.RELATED_TO,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_entity_type_whitespace(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": " PERSON "}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_called_once_with(
            entity_id="ent1",
            name="Entity 1",
            entity_type=EntityType.PERSON,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_relationship_type_whitespace(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": " RELATED_TO "}]}'
        mock_knowledge_graph.query_entity.side_effect = [Mock(entity_id="ent1"), Mock(entity_id="ent2")]
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_called_once_with(
            relationship_id="rel1",
            source_entity_id="ent1",
            target_entity_id="ent2",
            relationship_type=RelationType.RELATED_TO,
            attributes={}
        )

    @pytest.mark.asyncio
    async def test_process_reflection_output_entity_type_not_in_enum(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [{"entity_id": "ent1", "name": "Entity 1", "entity_type": "NON_EXISTENT"}], "relationships": []}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_reflection_output_relationship_type_not_in_enum(self, reflection_engine, mock_knowledge_graph):
        reflection_output = '{"entities": [], "relationships": [{"relationship_id": "rel1", "source_entity_id": "ent1", "target_entity_id": "ent2", "relationship_type": "NON_EXISTENT"}]}'
        await reflection_engine._process_reflection_output(reflection_output)
        mock_knowledge_graph.add_relationship.assert_not_called()
