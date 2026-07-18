"""وحدة Workflow Context.

تتولى هذه الوحدة مسؤولية إدارة سياق تنفيذ تدفقات العمل (Workflows)،
بما في ذلك البيانات، المتغيرات، وحالة التنفيذ.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger(__name__)


class IWorkflowContext(ABC):
    """واجهة مجردة لـ Workflow Context.

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لـ Workflow Context.
    """

    @abstractmethod
    async def get_context(self, workflow_id: str) -> Dict[str, Any]:  # noqa: E501
        """الحصول على سياق تدفق عمل معين.

        Args:
            workflow_id (str): معرف تدفق العمل.

        Returns:
            Dict[str, Any]: قاموس يحتوي على سياق تدفق العمل.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_context(self, workflow_id: str, updates: Dict[str, Any]) -> None:  # noqa: E501
        """تحديث سياق تدفق عمل معين.

        Args:
            workflow_id (str): معرف تدفق العمل.
            updates (Dict[str, Any]): التحديثات المراد تطبيقها على السياق.
        """
        raise NotImplementedError


class WorkflowContext(IWorkflowContext):
    """تنفيذ Workflow Context.

    مسؤول عن إدارة سياق تنفيذ تدفقات العمل.
    """

    def __init__(self) -> None:
        self._contexts: Dict[str, Dict[str, Any]] = {}
        logger.info("WorkflowContext instance created.")

    async def get_context(self, workflow_id: str) -> Dict[str, Any]:  # noqa: E501
        return self._contexts.get(workflow_id, {})

    async def update_context(self, workflow_id: str, updates: Dict[str, Any]) -> None:  # noqa: E501
        if workflow_id not in self._contexts:
            self._contexts[workflow_id] = {}
        self._contexts[workflow_id].update(updates)
        logger.info("Workflow \"%s\" context updated with: %s", workflow_id, updates)  # noqa: E501
