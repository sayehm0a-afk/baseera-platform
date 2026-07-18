import pytest
from core.autonomous_intelligence_layer.context_manager.context_manager import ContextManager

def test_context_manager_initialization():
    """اختبار تهيئة ContextManager بدون سياق عام."""
    manager = ContextManager()
    assert manager.get_shared_context() == {}

def test_context_manager_initialization_with_global_context():
    """اختبار تهيئة ContextManager بسياق عام أولي."""
    initial_context = {"user": "test_user", "session_id": "123"}
    manager = ContextManager(global_context=initial_context)
    assert manager.get_shared_context() == initial_context

def test_get_shared_context():
    """اختبار استرداد السياق المشترك."""
    initial_context = {"user": "test_user"}
    manager = ContextManager(global_context=initial_context)
    shared_context = manager.get_shared_context()
    assert shared_context == initial_context
    # التأكد من أنها نسخة وليست نفس الكائن
    assert shared_context is not initial_context

def test_update_shared_context():
    """اختبار تحديث السياق المشترك."""
    manager = ContextManager(global_context={"key1": "value1"})
    manager.update_shared_context({"key2": "value2", "key1": "new_value1"})
    assert manager.get_shared_context() == {"key1": "new_value1", "key2": "value2"}

def test_get_isolated_context():
    """اختبار استرداد سياق معزول."""
    manager = ContextManager()
    manager.store_isolated_context("task_context_1", {"task_id": "T1", "status": "RUNNING"})
    context = manager.get_isolated_context("task_context_1")
    assert context == {"task_id": "T1", "status": "RUNNING"}

def test_get_non_existent_isolated_context():
    """اختبار استرداد سياق معزول غير موجود."""
    manager = ContextManager()
    context = manager.get_isolated_context("non_existent")
    assert context == {}

def test_store_isolated_context():
    """اختبار تخزين سياق معزول."""
    manager = ContextManager()
    manager.store_isolated_context("task_context_2", {"task_id": "T2", "agent": "A1"})
    assert manager.get_isolated_context("task_context_2") == {"task_id": "T2", "agent": "A1"}

def test_get_inherited_context():
    """اختبار استرداد سياق موروث."""
    manager = ContextManager()
    manager.store_isolated_context("parent_context", {"p_key1": "p_val1", "common_key": "p_common"})
    manager.store_isolated_context("child_context", {"c_key1": "c_val1", "common_key": "c_common"})
    inherited = manager.get_inherited_context("parent_context", "child_context")
    assert inherited == {"p_key1": "p_val1", "c_key1": "c_val1", "common_key": "c_common"}

def test_get_inherited_context_only_parent():
    """اختبار استرداد سياق موروث بوجود سياق أب فقط."""
    manager = ContextManager()
    manager.store_isolated_context("parent_context_only", {"p_key": "p_val"})
    inherited = manager.get_inherited_context("parent_context_only", "non_existent_child")
    assert inherited == {"p_key": "p_val"}

def test_get_inherited_context_only_child():
    """اختبار استرداد سياق موروث بوجود سياق ابن فقط."""
    manager = ContextManager()
    manager.store_isolated_context("child_context_only", {"c_key": "c_val"})
    inherited = manager.get_inherited_context("non_existent_parent", "child_context_only")
    assert inherited == {"c_key": "c_val"}

def test_compress_context_default_strategy():
    """اختبار ضغط السياق بالاستراتيجية الافتراضية."""
    manager = ContextManager()
    long_string = "a" * 150
    context = {"short": "abc", "long": long_string, "number": 123}
    compressed = manager.compress_context(context)
    assert compressed == {"short": "abc", "number": 123}
    assert "long" not in compressed

def test_compress_context_unknown_strategy():
    """اختبار ضغط السياق باستراتيجية غير معروفة."""
    manager = ContextManager()
    context = {"short": "abc", "long": "a" * 150}
    compressed = manager.compress_context(context, strategy="unknown")
    assert compressed == context

def test_filter_context():
    """اختبار تصفية السياق."""
    manager = ContextManager()
    context = {"key1": "val1", "key2": "val2", "key3": "val3"}
    filtered = manager.filter_context(context, keys_to_keep=["key1", "key3"])
    assert filtered == {"key1": "val1", "key3": "val3"}

def test_filter_context_no_keys_to_keep():
    """اختبار تصفية السياق بدون مفاتيح للحفاظ عليها."""
    manager = ContextManager()
    context = {"key1": "val1", "key2": "val2"}
    filtered = manager.filter_context(context, keys_to_keep=None)
    assert filtered == context

def test_filter_context_non_existent_keys():
    """اختبار تصفية السياق بمفاتيح غير موجودة."""
    manager = ContextManager()
    context = {"key1": "val1"}
    filtered = manager.filter_context(context, keys_to_keep=["key1", "non_existent"])
    assert filtered == {"key1": "val1"}

def test_merge_context():
    """اختبار دمج سياقات متعددة."""
    manager = ContextManager()
    context1 = {"a": 1, "b": 2}
    context2 = {"b": 3, "c": 4}
    context3 = {"d": 5}
    merged = manager.merge_context(context1, context2, context3)
    assert merged == {"a": 1, "b": 3, "c": 4, "d": 5}

def test_merge_context_empty_contexts():
    """اختبار دمج سياقات فارغة."""
    manager = ContextManager()
    merged = manager.merge_context({}, {}, {"a": 1})
    assert merged == {"a": 1}

def test_delete_isolated_context():
    """اختبار حذف سياق معزول."""
    manager = ContextManager()
    manager.store_isolated_context("to_delete", {"data": "value"})
    assert manager.get_isolated_context("to_delete") == {"data": "value"}
    manager.delete_isolated_context("to_delete")
    assert manager.get_isolated_context("to_delete") == {}

def test_context_manager_repr():
    """اختبار تمثيل السلسلة النصية لـ ContextManager."""
    manager = ContextManager(global_context={"g_key": "g_val"})
    manager.store_isolated_context("iso_key", {"i_key": "i_val"})
    repr_str = repr(manager)
    assert "ContextManager(global_context_keys=['g_key']" in repr_str
    assert "stored_contexts_count=1)" in repr_str
