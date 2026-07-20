from typing import Any, Dict, List, Optional


class ContextStore:
    """
    متجر مركزي لإدارة سياقات المهام والوكلاء.

    يوفر آليات لتخزين واسترداد السياق بشكل آمن ومنظم.
    """

    def __init__(self):
        """
        يهيئ مثيلًا جديدًا لـ ContextStore.
        """
        self._store: Dict[str, Any] = {}

    def store_context(self, key: str, context: Any) -> None:
        """
        يخزن سياقًا معينًا باستخدام مفتاح.

        Args:
            key (str): المفتاح الفريد للسياق.
            context (Any): بيانات السياق المراد تخزينها.

        Raises:
            ValueError: إذا كان المفتاح فارغًا.
        """
        if not key:
            raise ValueError("المفتاح (key) لا يمكن أن يكون فارغًا.")
        self._store[key] = context

    def retrieve_context(self, key: str) -> Optional[Any]:
        """
        يسترد سياقًا معينًا باستخدام مفتاح.

        Args:
            key (str): المفتاح الفريد للسياق.

        Returns:
            Optional[Any]: بيانات السياق المخزنة، أو None إذا لم يتم العثور على المفتاح.

        Raises:
            ValueError: إذا كان المفتاح فارغًا.
        """
        if not key:
            raise ValueError("المفتاح (key) لا يمكن أن يكون فارغًا.")
        return self._store.get(key)

    def delete_context(self, key: str) -> None:
        """
        يحذف سياقًا معينًا باستخدام مفتاح.

        Args:
            key (str): المفتاح الفريد للسياق.

        Raises:
            ValueError: إذا كان المفتاح فارغًا.
        """
        if not key:
            raise ValueError("المفتاح (key) لا يمكن أن يكون فارغًا.")
        if key in self._store:
            del self._store[key]

    def list_keys(self) -> List[str]:
        """
        يسرد جميع المفاتيح المخزنة في المتجر.

        Returns:
            List[str]: قائمة بالمفاتيح.
        """
        return list(self._store.keys())

    def clear(self) -> None:
        """
        يمسح جميع السياقات المخزنة.
        """
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __repr__(self) -> str:
        return f"ContextStore(keys={list(self._store.keys())})"
