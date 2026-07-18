import pytest
from core.autonomous_intelligence_layer.context_manager.context_store import ContextStore

def test_context_store_initialization():
    """اختبار تهيئة ContextStore."""
    store = ContextStore()
    assert len(store) == 0

def test_store_and_retrieve_context():
    """اختبار تخزين واسترداد السياق."""
    store = ContextStore()
    store.store_context("key1", {"data": "value1"})
    retrieved = store.retrieve_context("key1")
    assert retrieved == {"data": "value1"}
    assert len(store) == 1

def test_retrieve_non_existent_context():
    """اختبار استرداد سياق غير موجود."""
    store = ContextStore()
    retrieved = store.retrieve_context("non_existent_key")
    assert retrieved is None

def test_store_context_with_empty_key_raises_error():
    """اختبار تخزين السياق بمفتاح فارغ يرفع خطأ."""
    store = ContextStore()
    with pytest.raises(ValueError, match="المفتاح \(key\) لا يمكن أن يكون فارغًا."):
        store.store_context("", {"data": "value"})

def test_retrieve_context_with_empty_key_raises_error():
    """اختبار استرداد السياق بمفتاح فارغ يرفع خطأ."""
    store = ContextStore()
    with pytest.raises(ValueError, match="المفتاح \(key\) لا يمكن أن يكون فارغًا."):
        store.retrieve_context("")

def test_delete_context():
    """اختبار حذف السياق."""
    store = ContextStore()
    store.store_context("key1", {"data": "value1"})
    assert "key1" in store
    store.delete_context("key1")
    assert "key1" not in store
    assert len(store) == 0

def test_delete_non_existent_context():
    """اختبار حذف سياق غير موجود لا يسبب خطأ."""
    store = ContextStore()
    store.delete_context("non_existent_key") # Should not raise an error
    assert len(store) == 0

def test_delete_context_with_empty_key_raises_error():
    """اختبار حذف السياق بمفتاح فارغ يرفع خطأ."""
    store = ContextStore()
    with pytest.raises(ValueError, match="المفتاح \(key\) لا يمكن أن يكون فارغًا."):
        store.delete_context("")

def test_list_keys():
    """اختبار سرد جميع المفاتيح."""
    store = ContextStore()
    store.store_context("key1", 1)
    store.store_context("key2", 2)
    keys = store.list_keys()
    assert sorted(keys) == ["key1", "key2"]

def test_clear_store():
    """اختبار مسح جميع السياقات."""
    store = ContextStore()
    store.store_context("key1", 1)
    store.store_context("key2", 2)
    assert len(store) == 2
    store.clear()
    assert len(store) == 0
    assert store.retrieve_context("key1") is None

def test_contains_method():
    """اختبار طريقة __contains__."""
    store = ContextStore()
    store.store_context("key_exists", "data")
    assert "key_exists" in store
    assert "key_not_exists" not in store

def test_context_store_repr():
    """اختبار تمثيل السلسلة النصية لـ ContextStore."""
    store = ContextStore()
    store.store_context("k1", "v1")
    store.store_context("k2", "v2")
    repr_str = repr(store)
    assert "ContextStore(keys=['k1', 'k2'])" in repr_str or "ContextStore(keys=['k2', 'k1'])" in repr_str
