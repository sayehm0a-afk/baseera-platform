"""
Knowledge Graph Module

This module implements the Knowledge Graph, which manages entities, relationships,
and attributes with operations for ingestion, querying, traversal, entity resolution,
relationship extraction, conflict detection, and knowledge updates.
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EntityType(Enum):
    """Enumeration for entity types."""

    COMPANY = "company"
    PERSON = "person"
    FINANCIAL_INSTRUMENT = "financial_instrument"
    MARKET_INDEX = "market_index"
    ECONOMIC_INDICATOR = "economic_indicator"
    CONCEPT = "concept"
    EVENT = "event"
    OTHER = "other"


class RelationType(Enum):
    """Enumeration for relationship types."""

    OWNS = "owns"
    MANAGES = "manages"
    WORKS_FOR = "works_for"
    INVESTS_IN = "invests_in"
    AFFECTS = "affects"
    CORRELATES_WITH = "correlates_with"
    RELATED_TO = "related_to"
    PARENT_OF = "parent_of"
    CHILD_OF = "child_of"
    OTHER = "other"


@dataclass
class KnowledgeEntity:
    """Represents an entity in the knowledge graph."""

    entity_id: str
    name: str
    entity_type: EntityType
    attributes: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    confidence: float = 1.0  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeRelationship:
    """Represents a relationship between entities."""

    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: RelationType
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # 0.0 to 1.0
    source: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraphConfig:
    """Configuration for Knowledge Graph."""

    max_entities: int = 100000
    max_relationships: int = 500000
    enable_entity_resolution: bool = True
    enable_relationship_extraction: bool = True
    enable_conflict_detection: bool = True
    enable_versioning: bool = True
    conflict_threshold: float = 0.3  # Threshold for detecting conflicts


class KnowledgeGraph:
    """
    Knowledge Graph for managing entities, relationships, and attributes.

    The Knowledge Graph is responsible for:
    - Ingesting structured and unstructured data
    - Storing entities and relationships
    - Querying and traversing the graph
    - Entity resolution and relationship extraction
    - Conflict detection
    - Knowledge updates and versioning
    - Permission-based access control
    """

    def __init__(self, config: Optional[KnowledgeGraphConfig] = None):
        """
        Initialize the Knowledge Graph.

        Args:
            config: KnowledgeGraphConfig instance for configuring graph behavior.
                   If None, uses default config.
        """
        self.config = config or KnowledgeGraphConfig()
        self.entities: Dict[str, KnowledgeEntity] = {}
        self.relationships: Dict[str, KnowledgeRelationship] = {}
        self.entity_index: Dict[str, Set[str]] = {}  # Index by entity name
        self.conflict_log: List[Dict[str, Any]] = []

    def add_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: EntityType,
        attributes: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        confidence: float = 1.0,
    ) -> KnowledgeEntity:
        """
        Add an entity to the knowledge graph.

        Args:
            entity_id: Unique identifier for the entity
            name: Name of the entity
            entity_type: Type of the entity
            attributes: Optional attributes of the entity
            source: Optional source of the entity information
            confidence: Confidence level (0.0 to 1.0)

        Returns:
            KnowledgeEntity representing the added entity
        """
        # Check if entity already exists
        if entity_id in self.entities:
            logger.warning(f"Entity {entity_id} already exists. Updating...")
            return self._update_entity(entity_id, attributes, confidence)

        # Create entity
        entity = KnowledgeEntity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            attributes=attributes or {},
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
        )

        # Add to graph
        self.entities[entity_id] = entity

        # Update index
        if name not in self.entity_index:
            self.entity_index[name] = set()
        self.entity_index[name].add(entity_id)

        logger.debug(f"Entity added: {entity_id}")
        return entity

    def add_relationship(
        self,
        relationship_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: RelationType,
        attributes: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        confidence: float = 1.0,
    ) -> KnowledgeRelationship:
        """
        Add a relationship between entities.

        Args:
            relationship_id: Unique identifier for the relationship
            source_entity_id: ID of the source entity
            target_entity_id: ID of the target entity
            relationship_type: Type of the relationship
            attributes: Optional attributes of the relationship
            source: Optional source of the relationship information
            confidence: Confidence level (0.0 to 1.0)

        Returns:
            KnowledgeRelationship representing the added relationship
        """
        # Verify entities exist
        if source_entity_id not in self.entities:
            logger.error(f"Source entity {source_entity_id} not found")
            raise ValueError(f"Source entity {source_entity_id} not found")

        if target_entity_id not in self.entities:
            logger.error(f"Target entity {target_entity_id} not found")
            raise ValueError(f"Target entity {target_entity_id} not found")

        # Create relationship
        relationship = KnowledgeRelationship(
            relationship_id=relationship_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type=relationship_type,
            attributes=attributes or {},
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
        )

        # Add to graph
        self.relationships[relationship_id] = relationship

        logger.debug(f"Relationship added: {relationship_id}")
        return relationship

    def query_entity(self, entity_id: str) -> Optional[KnowledgeEntity]:
        """
        Query an entity by ID.

        Args:
            entity_id: The entity ID to query

        Returns:
            KnowledgeEntity if found, None otherwise
        """
        return self.entities.get(entity_id)

    def query_entities_by_name(self, name: str) -> List[KnowledgeEntity]:
        """
        Query entities by name.

        Args:
            name: The entity name to query

        Returns:
            List of KnowledgeEntity objects matching the name
        """
        entity_ids = self.entity_index.get(name, set())
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]

    def query_entities_by_type(self, entity_type: EntityType) -> List[KnowledgeEntity]:
        """
        Query entities by type.

        Args:
            entity_type: The entity type to query

        Returns:
            List of KnowledgeEntity objects of the specified type
        """
        return [
            entity
            for entity in self.entities.values()
            if entity.entity_type == entity_type
        ]

    def traverse(
        self,
        start_entity_id: str,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """
        Traverse the knowledge graph starting from an entity.

        Args:
            start_entity_id: The starting entity ID
            max_depth: Maximum traversal depth

        Returns:
            Dictionary containing traversal results
        """
        if start_entity_id not in self.entities:
            logger.error(f"Start entity {start_entity_id} not found")
            return {}

        visited = set()
        queue = [(start_entity_id, 0)]
        traversal_result = {
            "start_entity": start_entity_id,
            "entities": set(),
            "relationships": set(),
            "depth": max_depth,
        }

        while queue:
            entity_id, depth = queue.pop(0)

            if depth > max_depth or entity_id in visited:
                continue

            visited.add(entity_id)
            traversal_result["entities"].add(entity_id)

            # Find related entities
            for rel_id, relationship in self.relationships.items():
                if relationship.source_entity_id == entity_id:
                    target_id = relationship.target_entity_id
                    traversal_result["relationships"].add(rel_id)

                    if target_id not in visited:
                        queue.append((target_id, depth + 1))

                elif relationship.target_entity_id == entity_id:
                    source_id = relationship.source_entity_id
                    traversal_result["relationships"].add(rel_id)

                    if source_id not in visited:
                        queue.append((source_id, depth + 1))

        traversal_result["entities"] = list(traversal_result["entities"])
        traversal_result["relationships"] = list(traversal_result["relationships"])
        return traversal_result

    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """
        Detect conflicts in the knowledge graph.

        Returns:
            List of detected conflicts
        """
        conflicts = []

        # Check for conflicting relationships
        for rel_id, relationship in self.relationships.items():
            if not relationship.is_valid:
                continue

            # Look for conflicting relationships
            for other_rel_id, other_rel in self.relationships.items():
                if rel_id == other_rel_id or not other_rel.is_valid:
                    continue

                # Check if relationships are between same entities but different types
                if (
                    relationship.source_entity_id == other_rel.source_entity_id
                    and relationship.target_entity_id == other_rel.target_entity_id
                    and relationship.relationship_type != other_rel.relationship_type
                ):

                    # Calculate conflict score
                    conflict_score = abs(relationship.confidence - other_rel.confidence)

                    if conflict_score > self.config.conflict_threshold:
                        conflicts.append(
                            {
                                "type": "relationship_conflict",
                                "relationship_1": rel_id,
                                "relationship_2": other_rel_id,
                                "conflict_score": conflict_score,
                                "timestamp": datetime.now(UTC),
                            }
                        )

        self.conflict_log.extend(conflicts)
        logger.debug(f"Detected {len(conflicts)} conflicts")
        return conflicts

    def resolve_entity(self, entity_name: str) -> Optional[KnowledgeEntity]:
        """
        Resolve an entity by name (returns the most confident entity).

        Args:
            entity_name: The entity name to resolve

        Returns:
            KnowledgeEntity with highest confidence, or None
        """
        entities = self.query_entities_by_name(entity_name)

        if not entities:
            return None

        # Return entity with highest confidence
        return max(entities, key=lambda e: e.confidence)

    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge graph.

        Returns:
            Dictionary containing graph statistics
        """
        entity_types = {}
        for entity_type in EntityType:
            count = len(self.query_entities_by_type(entity_type))
            if count > 0:
                entity_types[entity_type.value] = count

        relationship_types = {}
        for rel_type in RelationType:
            count = len(
                [
                    r
                    for r in self.relationships.values()
                    if r.relationship_type == rel_type
                ]
            )
            if count > 0:
                relationship_types[rel_type.value] = count

        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
            "entity_types": entity_types,
            "relationship_types": relationship_types,
            "conflicts": len(self.conflict_log),
        }

    def _update_entity(
        self,
        entity_id: str,
        attributes: Optional[Dict[str, Any]],
        confidence: float,
    ) -> KnowledgeEntity:
        """
        Update an existing entity.

        Args:
            entity_id: The entity ID to update
            attributes: New attributes to merge
            confidence: New confidence level

        Returns:
            Updated KnowledgeEntity
        """
        entity = self.entities[entity_id]

        if self.config.enable_versioning:
            entity.version += 1

        if attributes:
            entity.attributes.update(attributes)

        entity.confidence = max(0.0, min(1.0, confidence))
        entity.timestamp = datetime.now(UTC)

        logger.debug(f"Entity updated: {entity_id}")
        return entity

    def invalidate_entity(self, entity_id: str) -> None:
        """
        Invalidate an entity (mark as no longer valid).

        Args:
            entity_id: The entity ID to invalidate
        """
        if entity_id in self.entities:
            self.entities[entity_id].is_valid = False
            logger.debug(f"Entity invalidated: {entity_id}")

    def invalidate_relationship(self, relationship_id: str) -> None:
        """
        Invalidate a relationship (mark as no longer valid).

        Args:
            relationship_id: The relationship ID to invalidate
        """
        if relationship_id in self.relationships:
            self.relationships[relationship_id].is_valid = False
            logger.debug(f"Relationship invalidated: {relationship_id}")

    def __repr__(self) -> str:
        """
        Return a string representation of the KnowledgeGraph.
        """
        active_entities = sum(1 for entity in self.entities.values() if entity.is_valid)
        active_relationships = sum(
            1 for rel in self.relationships.values() if rel.is_valid
        )
        return f"KnowledgeGraph(active_entities={active_entities}, relationships={active_relationships})"
