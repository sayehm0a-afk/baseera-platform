from typing import Any, Dict, List, Optional
from .context_store import ContextStore

class ContextManager:
    """
    يدير السياق بذكاء بين الوكلاء والمهام في طبقة الذكاء الاصطناعي المستقل.

    يوفر آليات للسياق المشترك، المعزول، والموروث، بالإضافة إلى ضغط السياق، وتصفيته، ودمجه.
    """

    def __init__(self, global_context: Optional[Dict[str, Any]] = None):
        """
        يهيئ مثيلًا جديدًا لـ ContextManager.

        Args:
            global_context (Optional[Dict[str, Any]]): السياق العام الأولي الذي يمكن مشاركته.
        """
        self._global_context = global_context if global_context is not None else {}
        self._context_store = ContextStore()

    def get_shared_context(self) -> Dict[str, Any]:
        """
        يسترد السياق المشترك (العام).

        Returns:
            Dict[str, Any]: نسخة من السياق المشترك.
        """
        return self._global_context.copy()

    def update_shared_context(self, updates: Dict[str, Any]) -> None:
        """
        يحدث السياق المشترك.

        Args:
            updates (Dict[str, Any]): قاموس يحتوي على التحديثات المراد تطبيقها على السياق المشترك.
        """
        self._global_context.update(updates)

    def get_isolated_context(self, context_id: str) -> Dict[str, Any]:
        """
        يسترد سياقًا معزولًا بمعرف محدد.

        Args:
            context_id (str): معرف السياق المعزول.

        Returns:
            Dict[str, Any]: السياق المعزول، أو قاموس فارغ إذا لم يتم العثور عليه.
        """
        return self._context_store.retrieve_context(context_id) or {}

    def store_isolated_context(self, context_id: str, context_data: Dict[str, Any]) -> None:
        """
        يخزن سياقًا معزولًا بمعرف محدد.

        Args:
            context_id (str): معرف السياق المعزول.
            context_data (Dict[str, Any]): بيانات السياق المراد تخزينها.
        """
        self._context_store.store_context(context_id, context_data)

    def get_inherited_context(self, parent_context_id: str, current_context_id: str) -> Dict[str, Any]:
        """
        يسترد سياقًا موروثًا من سياق أب، مع دمج السياق الحالي.

        Args:
            parent_context_id (str): معرف سياق الأب.
            current_context_id (str): معرف السياق الحالي.

        Returns:
            Dict[str, Any]: السياق الموروث والمدمج.
        """
        parent_context = self.get_isolated_context(parent_context_id)
        current_context = self.get_isolated_context(current_context_id)
        # الدمج: السياق الحالي يلغي قيم السياق الأب إذا كانت موجودة
        inherited_context = {**parent_context, **current_context}
        return inherited_context

    def compress_context(self, context: Dict[str, Any], strategy: str = "default") -> Dict[str, Any]:
        """
        يضغط السياق بناءً على استراتيجية محددة.

        (ملاحظة: هذا تنفيذ وهمي. في تطبيق حقيقي، قد يتضمن تقنيات مثل التلخيص، إزالة التكرارات، أو تقليل الأبعاد.)

        Args:
            context (Dict[str, Any]): السياق المراد ضغطه.
            strategy (str): استراتيجية الضغط (افتراضي: "default").

        Returns:
            Dict[str, Any]: السياق المضغوط.
        """
        if strategy == "default":
            # مثال بسيط: إزالة المفاتيح الكبيرة جدًا أو غير الضرورية
            compressed_context = {k: v for k, v in context.items() if len(str(v)) < 100}
            return compressed_context
        return context # لا يوجد ضغط إذا لم يتم التعرف على الاستراتيجية

    def filter_context(self, context: Dict[str, Any], keys_to_keep: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        يقوم بتصفية السياق للاحتفاظ بمفاتيح محددة فقط.

        Args:
            context (Dict[str, Any]): السياق المراد تصفيته.
            keys_to_keep (Optional[List[str]]): قائمة بالمفاتيح المراد الاحتفاظ بها. إذا كانت None، يتم إرجاع السياق كما هو.

        Returns:
            Dict[str, Any]: السياق المصفى.
        """
        if keys_to_keep is None:
            return context
        return {key: context[key] for key in keys_to_keep if key in context}

    def merge_context(self, *contexts: Dict[str, Any]) -> Dict[str, Any]:
        """
        يدمج سياقات متعددة في سياق واحد.

        تتم عملية الدمج بترتيب تمرير السياقات، حيث تلغي القيم اللاحقة القيم السابقة.

        Args:
            *contexts (Dict[str, Any]): عدد متغير من قواميس السياق للدمج.

        Returns:
            Dict[str, Any]: السياق المدمج.
        """
        merged_context = {}
        for context in contexts:
            merged_context.update(context)
        return merged_context

    def update_isolated_context(self, context_id: str, updates: Dict[str, Any]) -> None:
        """
        يحدث سياقًا معزولًا موجودًا.

        Args:
            context_id (str): معرف السياق المعزول المراد تحديثه.
            updates (Dict[str, Any]): قاموس يحتوي على التحديثات المراد تطبيقها.

        Raises:
            ValueError: إذا لم يكن السياق المعزول موجودًا.
        """
        if context_id not in self._context_store.list_keys():
            raise ValueError(f"السياق المعزول ذو المعرف {context_id} غير موجود.")
        current_context = self._context_store.retrieve_context(context_id)
        current_context.update(updates)
        self._context_store.store_context(context_id, current_context)

    def delete_isolated_context(self, context_id: str) -> None:
        """
        يحذف سياقًا معزولًا بمعرف محدد.

        Args:
            context_id (str): معرف السياق المعزول المراد حذفه.
        """
        self._context_store.delete_context(context_id)

    def __repr__(self) -> str:
        return f"ContextManager(global_context_keys={list(self._global_context.keys())}, stored_contexts_count={len(self._context_store)})"
