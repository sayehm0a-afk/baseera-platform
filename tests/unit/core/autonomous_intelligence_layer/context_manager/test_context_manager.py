import pytest
from unittest.mock import Mock
from src.core.autonomous_intelligence_layer.context_manager.context_manager import ContextManager
from src.core.autonomous_intelligence_layer.context_manager.context_store import ContextStore


class TestContextManager:
    @pytest.fixture
    def context_store_mock(self):
        mock = Mock(spec=ContextStore)
        mock.__len__ = Mock(return_value=0)  # Mock the __len__ method
        return mock

    @pytest.fixture
    def context_manager(self, context_store_mock):
        return ContextManager(context_store=context_store_mock)

    def test_initialization(self, context_manager, context_store_mock):
        assert context_manager is not None
        assert context_manager._global_context == {}
        assert context_manager._context_store == context_store_mock

    def test_get_shared_context(self, context_manager):
        context_manager._global_context = {"key": "value"}
        shared_context = context_manager.get_shared_context()
        assert shared_context == {"key": "value"}
        assert shared_context is not context_manager._global_context  # Ensure a copy is returned

    def test_update_shared_context(self, context_manager):
        context_manager._global_context = {"key1": "value1"}
        updates = {"key2": "value2", "key1": "new_value1"}
        context_manager.update_shared_context(updates)
        assert context_manager._global_context == {"key1": "new_value1", "key2": "value2"}

    def test_get_isolated_context(self, context_manager, context_store_mock):
        context_id = "test_id"
        mock_data = {"data": "isolated"}
        context_store_mock.retrieve_context.return_value = mock_data
        result = context_manager.get_isolated_context(context_id)
        context_store_mock.retrieve_context.assert_called_once_with(context_id)
        assert result == mock_data

    def test_get_isolated_context_not_found(self, context_manager, context_store_mock):
        context_id = "non_existent"
        context_store_mock.retrieve_context.return_value = None
        result = context_manager.get_isolated_context(context_id)
        context_store_mock.retrieve_context.assert_called_once_with(context_id)
        assert result == {}

    def test_store_isolated_context(self, context_manager, context_store_mock):
        context_id = "test_id"
        context_data = {"data": "isolated"}
        context_manager.store_isolated_context(context_id, context_data)
        context_store_mock.store_context.assert_called_once_with(context_id, context_data)

    def test_get_inherited_context(self, context_manager, context_store_mock):
        parent_id = "parent_id"
        current_id = "current_id"
        parent_data = {"p_key": "p_value", "common_key": "p_common"}
        current_data = {"c_key": "c_value", "common_key": "c_common"}

        context_store_mock.retrieve_context.side_effect = [parent_data, current_data]

        result = context_manager.get_inherited_context(parent_id, current_id)

        assert context_store_mock.retrieve_context.call_count == 2
        context_store_mock.retrieve_context.assert_any_call(parent_id)
        context_store_mock.retrieve_context.assert_any_call(current_id)
        assert result == {"p_key": "p_value", "c_key": "c_value", "common_key": "c_common"}

    def test_compress_context_default_strategy(self, context_manager):
        context = {"short": "abc", "long": "a" * 150, "another_short": "xyz"}
        compressed = context_manager.compress_context(context)
        assert compressed == {"short": "abc", "another_short": "xyz"}

    def test_compress_context_unknown_strategy(self, context_manager):
        context = {"key": "value"}
        compressed = context_manager.compress_context(context, strategy="unknown")
        assert compressed == context

    def test_filter_context(self, context_manager):
        context = {"key1": "value1", "key2": "value2", "key3": "value3"}
        filtered = context_manager.filter_context(context, keys_to_keep=["key1", "key3"])
        assert filtered == {"key1": "value1", "key3": "value3"}

    def test_filter_context_no_keys_to_keep(self, context_manager):
        context = {"key1": "value1"}
        filtered = context_manager.filter_context(context, keys_to_keep=None)
        assert filtered == context

    def test_merge_context(self, context_manager):
        ctx1 = {"a": 1, "b": 2}
        ctx2 = {"b": 3, "c": 4}
        ctx3 = {"d": 5}
        merged = context_manager.merge_context(ctx1, ctx2, ctx3)
        assert merged == {"a": 1, "b": 3, "c": 4, "d": 5}

    def test_update_isolated_context(self, context_manager, context_store_mock):
        context_id = "test_id"
        initial_data = {"status": "pending", "user": "test"}
        updates = {"status": "completed", "timestamp": "now"}

        context_store_mock.list_keys.return_value = [context_id]
        context_store_mock.retrieve_context.return_value = initial_data.copy()

        context_manager.update_isolated_context(context_id, updates)

        context_store_mock.list_keys.assert_called_once()
        context_store_mock.retrieve_context.assert_called_once_with(context_id)
        context_store_mock.store_context.assert_called_once_with(context_id, {"status": "completed", "user": "test", "timestamp": "now"})

    def test_update_isolated_context_not_found(self, context_manager, context_store_mock):
        context_id = "non_existent"
        updates = {"status": "completed"}
        context_store_mock.list_keys.return_value = []

        with pytest.raises(ValueError, match=f"السياق المعزول ذو المعرف {context_id} غير موجود."):
            context_manager.update_isolated_context(context_id, updates)
        context_store_mock.list_keys.assert_called_once()
        context_store_mock.retrieve_context.assert_not_called()
        context_store_mock.store_context.assert_not_called()

    def test_delete_isolated_context(self, context_manager, context_store_mock):
        context_id = "test_id"
        context_manager.delete_isolated_context(context_id)
        context_store_mock.delete_context.assert_called_once_with(context_id)

    def test_repr(self, context_manager):
        context_manager._global_context = {"g_key": "g_value"}
        context_manager._context_store.list_keys.return_value = ["c_key1", "c_key2"]
        context_manager._context_store.__len__.return_value = 2
        expected_repr = "ContextManager(global_context_keys=['g_key'], stored_contexts_count=2)"
        assert repr(context_manager) == expected_repr
