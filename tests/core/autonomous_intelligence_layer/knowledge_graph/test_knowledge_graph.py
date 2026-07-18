"""
Unit tests for Knowledge Graph
"""

import pytest
from core.autonomous_intelligence_layer.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeEntity,
    KnowledgeRelationship,
    EntityType,
    RelationType,
    KnowledgeGraphConfig,
)


class TestKnowledgeGraph:
    """Test cases for KnowledgeGraph class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.graph = KnowledgeGraph()

    def test_knowledge_graph_initialization(self):
        """Test that KnowledgeGraph initializes correctly."""
        assert self.graph is not None
        assert self.graph.config is not None
        assert isinstance(self.graph.config, KnowledgeGraphConfig)
        assert len(self.graph.entities) == 0
        assert len(self.graph.relationships) == 0

    def test_knowledge_graph_with_custom_config(self):
        """Test KnowledgeGraph with custom config."""
        custom_config = KnowledgeGraphConfig(
            max_entities=50000,
            max_relationships=250000,
        )
        graph = KnowledgeGraph(config=custom_config)
        assert graph.config.max_entities == 50000
        assert graph.config.max_relationships == 250000

    def test_add_entity(self):
        """Test adding an entity to the graph."""
        entity = self.graph.add_entity(
            entity_id="company_001",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
            attributes={"sector": "Energy"},
            confidence=0.95,
        )

        assert entity is not None
        assert entity.entity_id == "company_001"
        assert entity.name == "Saudi Aramco"
        assert entity.entity_type == EntityType.COMPANY
        assert entity.confidence == 0.95

    def test_add_multiple_entities(self):
        """Test adding multiple entities."""
        self.graph.add_entity(
            entity_id="company_001",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
        )
        self.graph.add_entity(
            entity_id="person_001",
            name="John Doe",
            entity_type=EntityType.PERSON,
        )

        assert len(self.graph.entities) == 2

    def test_add_relationship(self):
        """Test adding a relationship between entities."""
        self.graph.add_entity(
            entity_id="company_001",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
        )
        self.graph.add_entity(
            entity_id="person_001",
            name="John Doe",
            entity_type=EntityType.PERSON,
        )

        relationship = self.graph.add_relationship(
            relationship_id="rel_001",
            source_entity_id="company_001",
            target_entity_id="person_001",
            relationship_type=RelationType.MANAGES,
            confidence=0.85,
        )

        assert relationship is not None
        assert relationship.relationship_type == RelationType.MANAGES
        assert relationship.confidence == 0.85

    def test_add_relationship_with_nonexistent_entity(self):
        """Test adding a relationship with nonexistent entities."""
        with pytest.raises(ValueError):
            self.graph.add_relationship(
                relationship_id="rel_001",
                source_entity_id="nonexistent_001",
                target_entity_id="nonexistent_002",
                relationship_type=RelationType.MANAGES,
            )

    def test_query_entity(self):
        """Test querying an entity by ID."""
        self.graph.add_entity(
            entity_id="company_001",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
        )

        entity = self.graph.query_entity("company_001")
        assert entity is not None
        assert entity.name == "Saudi Aramco"

    def test_query_nonexistent_entity(self):
        """Test querying a nonexistent entity."""
        entity = self.graph.query_entity("nonexistent")
        assert entity is None

    def test_query_entities_by_name(self):
        """Test querying entities by name."""
        self.graph.add_entity(
            entity_id="company_001",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
        )
        self.graph.add_entity(
            entity_id="company_002",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
        )

        entities = self.graph.query_entities_by_name("Saudi Aramco")
        assert len(entities) == 2

    def test_query_entities_by_type(self):
        """Test querying entities by type."""
        self.graph.add_entity(
            entity_id="company_001",
            name="Saudi Aramco",
            entity_type=EntityType.COMPANY,
        )
        self.graph.add_entity(
            entity_id="person_001",
            name="John Doe",
            entity_type=EntityType.PERSON,
        )

        companies = self.graph.query_entities_by_type(EntityType.COMPANY)
        assert len(companies) == 1
        assert companies[0].entity_id == "company_001"

    def test_traverse_graph(self):
        """Test traversing the knowledge graph."""
        # Create a simple graph structure
        self.graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        self.graph.add_entity("e2", "Entity 2", EntityType.PERSON)
        self.graph.add_entity("e3", "Entity 3", EntityType.CONCEPT)

        self.graph.add_relationship("r1", "e1", "e2", RelationType.MANAGES)
        self.graph.add_relationship("r2", "e2", "e3", RelationType.RELATED_TO)

        traversal = self.graph.traverse("e1", max_depth=2)

        assert "e1" in traversal["entities"]
        assert "e2" in traversal["entities"]
        assert "e3" in traversal["entities"]
        assert len(traversal["relationships"]) >= 2

    def test_detect_conflicts(self):
        """Test conflict detection."""
        # Create entities
        self.graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        self.graph.add_entity("e2", "Entity 2", EntityType.COMPANY)

        # Add conflicting relationships
        self.graph.add_relationship(
            "r1", "e1", "e2", RelationType.MANAGES, confidence=0.9
        )
        self.graph.add_relationship(
            "r2", "e1", "e2", RelationType.WORKS_FOR, confidence=0.1
        )

        conflicts = self.graph.detect_conflicts()
        # Should detect conflict due to high confidence difference
        assert len(conflicts) > 0

    def test_resolve_entity(self):
        """Test entity resolution."""
        # Add multiple entities with same name but different confidence
        self.graph.add_entity(
            "e1", "Saudi Aramco", EntityType.COMPANY, confidence=0.7
        )
        self.graph.add_entity(
            "e2", "Saudi Aramco", EntityType.COMPANY, confidence=0.95
        )

        resolved = self.graph.resolve_entity("Saudi Aramco")
        assert resolved is not None
        assert resolved.entity_id == "e2"  # Should return the most confident one

    def test_get_graph_stats(self):
        """Test getting graph statistics."""
        self.graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        self.graph.add_entity("e2", "Entity 2", EntityType.PERSON)
        self.graph.add_relationship("r1", "e1", "e2", RelationType.MANAGES)

        stats = self.graph.get_graph_stats()

        assert stats["total_entities"] == 2
        assert stats["total_relationships"] == 1
        assert EntityType.COMPANY.value in stats["entity_types"]
        assert EntityType.PERSON.value in stats["entity_types"]

    def test_invalidate_entity(self):
        """Test invalidating an entity."""
        self.graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        entity = self.graph.query_entity("e1")
        assert entity.is_valid is True

        self.graph.invalidate_entity("e1")
        entity = self.graph.query_entity("e1")
        assert entity.is_valid is False

    def test_invalidate_relationship(self):
        """Test invalidating a relationship."""
        self.graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        self.graph.add_entity("e2", "Entity 2", EntityType.PERSON)
        self.graph.add_relationship("r1", "e1", "e2", RelationType.MANAGES)

        relationship = self.graph.relationships["r1"]
        assert relationship.is_valid is True

        self.graph.invalidate_relationship("r1")
        relationship = self.graph.relationships["r1"]
        assert relationship.is_valid is False

    def test_confidence_clamping(self):
        """Test that confidence values are clamped to 0.0-1.0."""
        entity1 = self.graph.add_entity(
            "e1", "Entity 1", EntityType.COMPANY, confidence=1.5
        )
        entity2 = self.graph.add_entity(
            "e2", "Entity 2", EntityType.COMPANY, confidence=-0.5
        )

        assert entity1.confidence == 1.0
        assert entity2.confidence == 0.0

    def test_entity_attributes(self):
        """Test storing and retrieving entity attributes."""
        attributes = {"sector": "Energy", "market_cap": 2000000000000}
        entity = self.graph.add_entity(
            "e1", "Saudi Aramco", EntityType.COMPANY, attributes=attributes
        )

        assert entity.attributes == attributes

    def test_relationship_attributes(self):
        """Test storing and retrieving relationship attributes."""
        self.graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        self.graph.add_entity("e2", "Entity 2", EntityType.PERSON)

        attributes = {"role": "CEO", "since": 2020}
        relationship = self.graph.add_relationship(
            "r1", "e1", "e2", RelationType.MANAGES, attributes=attributes
        )

        assert relationship.attributes == attributes

    def test_entity_versioning(self):
        """Test entity versioning."""
        config = KnowledgeGraphConfig(enable_versioning=True)
        graph = KnowledgeGraph(config=config)

        entity = graph.add_entity("e1", "Entity 1", EntityType.COMPANY)
        assert entity.version == 1

        # Update entity
        graph._update_entity("e1", {"sector": "Energy"}, 0.9)
        entity = graph.query_entity("e1")
        assert entity.version == 2
