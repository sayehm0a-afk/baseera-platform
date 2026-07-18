"""
Unit tests for Memory Store
"""

import pytest
from datetime import datetime, timedelta
from core.autonomous_intelligence_layer.memory_reasoning import (
    MemoryStore,
    MemoryEntry,
    MemoryType,
    MemoryStoreConfig,
)


class TestMemoryStore:
    """Test cases for MemoryStore class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.store = MemoryStore()

    def test_memory_store_initialization(self):
        """Test that MemoryStore initializes correctly."""
        assert self.store is not None
        assert self.store.config is not None
        assert isinstance(self.store.config, MemoryStoreConfig)
        assert len(self.store.memory) == len(MemoryType)

    def test_memory_store_with_custom_config(self):
        """Test MemoryStore with custom config."""
        custom_config = MemoryStoreConfig(
            max_working_memory_entries=50,
            max_short_term_memory_entries=500,
        )
        store = MemoryStore(config=custom_config)
        assert store.config.max_working_memory_entries == 50
        assert store.config.max_short_term_memory_entries == 500

    def test_store_memory_entry(self):
        """Test storing a memory entry."""
        content = "Test memory content"
        entry = self.store.store(
            content=content,
            memory_type=MemoryType.SEMANTIC,
            source="test_source",
            confidence=0.95,
        )

        assert entry is not None
        assert entry.content == content
        assert entry.memory_type == MemoryType.SEMANTIC
        assert entry.source == "test_source"
        assert entry.confidence == 0.95

    def test_store_memory_with_tags(self):
        """Test storing memory with tags."""
        tags = ["finance", "market", "analysis"]
        entry = self.store.store(
            content="Market analysis",
            memory_type=MemoryType.SEMANTIC,
            tags=tags,
        )

        assert entry.tags == tags

    def test_retrieve_memory_entries(self):
        """Test retrieving memory entries."""
        self.store.store(
            content="Entry 1",
            memory_type=MemoryType.SEMANTIC,
        )
        self.store.store(
            content="Entry 2",
            memory_type=MemoryType.SEMANTIC,
        )

        entries = self.store.retrieve(MemoryType.SEMANTIC, limit=10)
        assert len(entries) == 2

    def test_search_memory_entries(self):
        """Test searching memory entries."""
        self.store.store(
            content="The market is bullish",
            memory_type=MemoryType.SEMANTIC,
        )
        self.store.store(
            content="The weather is sunny",
            memory_type=MemoryType.SEMANTIC,
        )

        results = self.store.search("market", limit=10)
        assert len(results) == 1
        assert "market" in results[0].content.lower()

    def test_search_across_memory_types(self):
        """Test searching across multiple memory types."""
        self.store.store(
            content="Financial data",
            memory_type=MemoryType.SEMANTIC,
        )
        self.store.store(
            content="Financial analysis",
            memory_type=MemoryType.EPISODIC,
        )

        results = self.store.search(
            "financial",
            memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC],
            limit=10,
        )
        assert len(results) == 2

    def test_rank_memory_entries(self):
        """Test ranking memory entries."""
        entry1 = self.store.store(
            content="High confidence entry",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
        )
        entry2 = self.store.store(
            content="Low confidence entry",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.3,
        )

        entries = [entry1, entry2]
        ranked = self.store.rank(entries)

        assert ranked[0].confidence >= ranked[1].confidence

    def test_summarize_memory_entries(self):
        """Test summarizing memory entries."""
        entry1 = self.store.store(
            content="First point",
            memory_type=MemoryType.SEMANTIC,
        )
        entry2 = self.store.store(
            content="Second point",
            memory_type=MemoryType.SEMANTIC,
        )

        summary = self.store.summarize([entry1, entry2])
        assert "First point" in summary
        assert "Second point" in summary

    def test_consolidate_memory(self):
        """Test consolidating memory entries."""
        # Disable deduplication to allow duplicate entries
        config = MemoryStoreConfig(enable_deduplication=False)
        store = MemoryStore(config=config)
        
        # Add duplicate entries
        store.store(
            content="Duplicate content",
            memory_type=MemoryType.SEMANTIC,
        )
        store.store(
            content="Duplicate content",
            memory_type=MemoryType.SEMANTIC,
        )

        assert len(store.memory[MemoryType.SEMANTIC]) == 2

        store.consolidate(MemoryType.SEMANTIC)

        assert len(store.memory[MemoryType.SEMANTIC]) == 1

    def test_memory_expiration(self):
        """Test memory entry expiration."""
        # Create a short-term memory entry with very short TTL
        config = MemoryStoreConfig(short_term_memory_ttl_hours=0)
        store = MemoryStore(config=config)

        entry = store.store(
            content="Short-lived content",
            memory_type=MemoryType.SHORT_TERM,
        )

        # Manually set expiration time to the past
        entry.expiration_time = datetime.utcnow() - timedelta(seconds=1)

        store.expire()

        # Entry should be archived or removed
        remaining_entries = store.memory[MemoryType.SHORT_TERM]
        assert len(remaining_entries) == 0 or remaining_entries[0].is_archived

    def test_memory_size_limits(self):
        """Test memory size limits enforcement."""
        config = MemoryStoreConfig(max_semantic_memory_entries=5)
        store = MemoryStore(config=config)

        # Add more entries than the limit
        for i in range(10):
            store.store(
                content=f"Entry {i}",
                memory_type=MemoryType.SEMANTIC,
            )

        # Should only have 5 entries
        assert len(store.memory[MemoryType.SEMANTIC]) == 5

    def test_memory_stats(self):
        """Test memory statistics."""
        self.store.store(
            content="Entry 1",
            memory_type=MemoryType.SEMANTIC,
        )
        self.store.store(
            content="Entry 2",
            memory_type=MemoryType.EPISODIC,
        )

        stats = self.store.get_memory_stats()

        assert "total_active_entries" in stats
        assert stats["total_active_entries"] == 2
        assert stats[MemoryType.SEMANTIC.value]["active_entries"] == 1
        assert stats[MemoryType.EPISODIC.value]["active_entries"] == 1

    def test_confidence_clamping(self):
        """Test that confidence values are clamped to 0.0-1.0."""
        entry1 = self.store.store(
            content="High confidence",
            memory_type=MemoryType.SEMANTIC,
            confidence=1.5,
        )
        entry2 = self.store.store(
            content="Negative confidence",
            memory_type=MemoryType.SEMANTIC,
            confidence=-0.5,
        )

        assert entry1.confidence == 1.0
        assert entry2.confidence == 0.0

    def test_memory_entry_access_tracking(self):
        """Test access tracking for memory entries."""
        entry = self.store.store(
            content="Test content",
            memory_type=MemoryType.SEMANTIC,
        )

        assert entry.access_count == 0
        assert entry.last_accessed is None

        # Retrieve the entry
        self.store.retrieve(MemoryType.SEMANTIC)

        # Access count should be incremented
        assert entry.access_count == 1
        assert entry.last_accessed is not None

    def test_deduplication_disabled(self):
        """Test that deduplication can be disabled."""
        config = MemoryStoreConfig(enable_deduplication=False)
        store = MemoryStore(config=config)

        store.store(
            content="Duplicate",
            memory_type=MemoryType.SEMANTIC,
        )
        store.store(
            content="Duplicate",
            memory_type=MemoryType.SEMANTIC,
        )

        # Both entries should be stored
        assert len(store.memory[MemoryType.SEMANTIC]) == 2

    def test_memory_entry_metadata(self):
        """Test storing and retrieving metadata."""
        metadata = {"key": "value", "number": 42}
        entry = self.store.store(
            content="Content with metadata",
            memory_type=MemoryType.SEMANTIC,
            metadata=metadata,
        )

        assert entry.metadata == metadata
