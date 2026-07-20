import pytest
from unittest.mock import Mock
from src.core.autonomous_intelligence_layer.memory_reasoning.memory_store import MemoryStore, MemoryType, MemoryEntry, MemoryStoreConfig
from datetime import datetime, timedelta, UTC

class TestMemoryStore:
    @pytest.fixture
    def memory_store(self):
        return MemoryStore()

    @pytest.fixture
    def sample_memory_entry(self):
        return MemoryEntry(
            memory_id="test_id",
            memory_type=MemoryType.WORKING,
            content="test content",
            source="test_source",
            confidence=0.9,
            tags=["tag1", "tag2"],
            metadata={"key": "value"},
            timestamp=datetime.now(UTC)
        )

    def test_initialization(self, memory_store):
        assert memory_store is not None
        assert memory_store.memory == {memory_type.value: [] for memory_type in MemoryType}
        assert memory_store.memory_index == {}
        assert isinstance(memory_store.config, MemoryStoreConfig)

    def test_store_memory(self, memory_store):
        content = "This is a test memory."
        memory_type = MemoryType.WORKING
        entry = memory_store.store(content=content, memory_type=memory_type)
        assert entry is not None
        assert entry.content == content
        assert entry.memory_type == memory_type
        assert entry.memory_id in memory_store.memory_index
        assert memory_store.memory_index[entry.memory_id] == entry
        assert entry in memory_store.memory[memory_type.value]

    def test_store_memory_with_metadata(self, memory_store):
        content = "Another test memory."
        memory_type = MemoryType.SHORT_TERM
        metadata = {"user": "test_user", "priority": 1}
        entry = memory_store.store(content=content, memory_type=memory_type, metadata=metadata)
        assert entry.metadata == metadata

    def test_retrieve_memory_by_type(self, memory_store, sample_memory_entry):
        memory_store.store(content=sample_memory_entry.content, memory_type=sample_memory_entry.memory_type)
        retrieved_entries = memory_store.retrieve(memory_type=MemoryType.WORKING)
        assert len(retrieved_entries) == 1
        assert retrieved_entries[0].content == sample_memory_entry.content

    def test_retrieve_non_existent_memory_type(self, memory_store):
        retrieved_entries = memory_store.retrieve(memory_type=MemoryType.EPISODIC)
        assert len(retrieved_entries) == 0

    def test_search_memory(self, memory_store):
        memory_store.store(content="apple banana cherry", memory_type=MemoryType.SEMANTIC)
        memory_store.store(content="date elderberry fig", memory_type=MemoryType.SEMANTIC)
        results = memory_store.search(query="banana")
        assert len(results) == 1
        assert results[0].content == "apple banana cherry"

    def test_search_memory_no_results(self, memory_store):
        memory_store.store(content="apple banana cherry", memory_type=MemoryType.SEMANTIC)
        results = memory_store.search(query="grape")
        assert len(results) == 0

    def test_delete_memory(self, memory_store, sample_memory_entry):
        entry = memory_store.store(content=sample_memory_entry.content, memory_type=sample_memory_entry.memory_type)
        memory_id = entry.memory_id
        assert memory_store.delete(memory_id) is True
        assert memory_id not in memory_store.memory_index
        assert not any(e.memory_id == memory_id for e in memory_store.memory[entry.memory_type.value])

    def test_delete_non_existent_memory(self, memory_store):
        assert memory_store.delete("non_existent_id") is False

    def test_len_memory_store(self, memory_store, sample_memory_entry):
        assert len(memory_store) == 0
        memory_store.store(content=sample_memory_entry.content, memory_type=sample_memory_entry.memory_type)
        assert len(memory_store) == 1

    def test_memory_contains(self, memory_store, sample_memory_entry):
        entry = memory_store.store(content=sample_memory_entry.content, memory_type=sample_memory_entry.memory_type)
        assert entry.memory_id in memory_store.memory_index
        assert "non_existent_id" not in memory_store.memory_index

    def test_rank_memory(self, memory_store):
        entry1 = memory_store.store(content="low confidence", memory_type=MemoryType.WORKING, confidence=0.1)
        entry2 = memory_store.store(content="high confidence", memory_type=MemoryType.WORKING, confidence=0.9)
        ranked = memory_store.rank([entry1, entry2])
        assert ranked[0].content == "high confidence"

    def test_summarize_memory(self, memory_store):
        entry1 = memory_store.store(content="This is the first sentence.", memory_type=MemoryType.WORKING)
        entry2 = memory_store.store(content="This is the second sentence.", memory_type=MemoryType.WORKING)
        summary = memory_store.summarize([entry1, entry2], max_summary_length=100)
        assert "This is the first sentence. | This is the second sentence." in summary
        assert len(summary) <= 100

    def test_consolidate_memory(self, memory_store):
        memory_store.store(content="duplicate content", memory_type=MemoryType.WORKING)
        memory_store.store(content="duplicate content", memory_type=MemoryType.WORKING)
        memory_store.store(content="unique content", memory_type=MemoryType.WORKING)
        assert len(memory_store.memory[MemoryType.WORKING.value]) == 2
        memory_store.consolidate(MemoryType.WORKING)
        assert len(memory_store.memory[MemoryType.WORKING.value]) == 2

    def test_expire_memory(self, memory_store):
        config = MemoryStoreConfig(short_term_memory_ttl_hours=0)
        memory_store_with_config = MemoryStore(config=config)
        entry = memory_store_with_config.store(content="expiring content", memory_type=MemoryType.SHORT_TERM)
        # Manually set timestamp to ensure it's expired
        entry.timestamp = datetime.now(UTC) - timedelta(hours=1)
        memory_store_with_config.expire()
        assert entry.is_archived is True

    def test_get_memory_stats(self, memory_store):
        memory_store.store(content="test1", memory_type=MemoryType.WORKING)
        memory_store.store(content="test2", memory_type=MemoryType.SHORT_TERM)
        stats = memory_store.get_memory_stats()
        assert stats["working"]["total_entries"] == 1
        assert stats["short_term"]["total_entries"] == 1
        assert stats["total_active_entries"] == 2

    def test_enforce_size_limits(self, memory_store):
        config = MemoryStoreConfig(max_working_memory_entries=1)
        memory_store_with_config = MemoryStore(config=config)
        entry1 = memory_store_with_config.store(content="old content", memory_type=MemoryType.WORKING)
        entry2 = memory_store_with_config.store(content="new content", memory_type=MemoryType.WORKING)
        assert len(memory_store_with_config.memory[MemoryType.WORKING.value]) == 1
        assert entry1 not in memory_store_with_config.memory[MemoryType.WORKING.value]
        assert entry2 in memory_store_with_config.memory[MemoryType.WORKING.value]


