import pytest
from src.core.autonomous_intelligence_layer.context_manager.context_store import ContextStore

@pytest.fixture
def context_store():
    return ContextStore()

def test_store_context(context_store):
    context_store.store_context("key1", "value1")
    assert context_store.retrieve_context("key1") == "value1"

def test_store_context_empty_key_raises_error(context_store):
    with pytest.raises(ValueError, match="المفتاح \(key\) لا يمكن أن يكون فارغًا."):
        context_store.store_context("", "value")

def test_retrieve_context(context_store):
    context_store.store_context("key1", "value1")
    assert context_store.retrieve_context("key1") == "value1"
    assert context_store.retrieve_context("nonexistent_key") is None

def test_retrieve_context_empty_key_raises_error(context_store):
    with pytest.raises(ValueError, match="المفتاح \(key\) لا يمكن أن يكون فارغًا."):
        context_store.retrieve_context("")

def test_delete_context(context_store):
    context_store.store_context("key1", "value1")
    context_store.delete_context("key1")
    assert context_store.retrieve_context("key1") is None

def test_delete_context_nonexistent_key(context_store):
    context_store.delete_context("nonexistent_key")  # Should not raise an error
    assert context_store.retrieve_context("nonexistent_key") is None

def test_delete_context_empty_key_raises_error(context_store):
    with pytest.raises(ValueError, match="المفتاح \(key\) لا يمكن أن يكون فارغًا."):
        context_store.delete_context("")

def test_list_keys(context_store):
    context_store.store_context("key1", "value1")
    context_store.store_context("key2", "value2")
    keys = context_store.list_keys()
    assert sorted(keys) == ["key1", "key2"]

def test_clear(context_store):
    context_store.store_context("key1", "value1")
    context_store.clear()
    assert len(context_store) == 0
    assert context_store.retrieve_context("key1") is None

def test_len(context_store):
    assert len(context_store) == 0
    context_store.store_context("key1", "value1")
    assert len(context_store) == 1
    context_store.store_context("key2", "value2")
    assert len(context_store) == 2

def test_contains(context_store):
    context_store.store_context("key1", "value1")
    assert "key1" in context_store
    assert "nonexistent_key" not in context_store

def test_repr(context_store):
    context_store.store_context("key1", "value1")
    context_store.store_context("key2", "value2")
    keys = sorted(list(context_store._store.keys()))
    expected_repr = f"ContextStore(keys={keys})"
    assert repr(context_store) == expected_repr
