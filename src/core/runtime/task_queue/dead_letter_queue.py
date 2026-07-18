import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class IDeadLetterQueue(ABC):
    """واجهة مجردة لقائمة انتظار الرسائل الميتة (Dead Letter Queue).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لقائمة انتظار الرسائل الميتة.
    """

    @abstractmethod
    async def enqueue(self, task_id: str, task_payload: Dict[str, Any], error: str) -> None:
        """يضيف مهمة فاشلة إلى قائمة انتظار الرسائل الميتة.

        Args:
            task_id (str): معرف المهمة الفاشلة.
            task_payload (Dict[str, Any]): حمولة (بيانات) المهمة الفاشلة.
            error (str): وصف الخطأ الذي تسبب في فشل المهمة.
        """
        raise NotImplementedError

    @abstractmethod
    async def dequeue(self, limit: int = 1) -> List[Dict[str, Any]]:
        """يسترد المهام من قائمة انتظار الرسائل الميتة.

        Args:
            limit (int): الحد الأقصى لعدد المهام المراد استردادها.

        Returns:
            List[Dict[str, Any]]: قائمة بالمهام الفاشلة.
        """
        raise NotImplementedError

    @abstractmethod
    async def remove(self, task_id: str) -> bool:
        """يزيل مهمة من قائمة انتظار الرسائل الميتة.

        Args:
            task_id (str): معرف المهمة المراد إزالتها.

        Returns:
            bool: True إذا تم إزالة المهمة بنجاح، False بخلاف ذلك.
        """
        raise NotImplementedError

    @abstractmethod
    async def size(self) -> int:
        """يعيد عدد المهام في قائمة انتظار الرسائل الميتة.

        Returns:
            int: عدد المهام.
        """
        raise NotImplementedError


class DeadLetterQueue(IDeadLetterQueue):
    """تنفيذ قائمة انتظار الرسائل الميتة (Dead Letter Queue).

    مسؤول عن تخزين المهام الفاشلة التي لا يمكن إعادة محاولتها.
    """

    def __init__(self) -> None:
        self._dlq: Dict[str, Dict[str, Any]] = {}
        logger.info("DeadLetterQueue instance created.")

    async def enqueue(self, task_id: str, task_payload: Dict[str, Any], error: str) -> None:
        if task_id in self._dlq:
            logger.warning("Task %s already in DLQ. Overwriting.", task_id)
        
        self._dlq[task_id] = {
            "task_id": task_id,
            "task_payload": task_payload,
            "error": error,
            "timestamp": datetime.now(datetime.UTC)
        }
        logger.info("Task %s enqueued to DLQ due to error: %s", task_id, error)

    async def dequeue(self, limit: int = 1) -> List[Dict[str, Any]]:
        dequeued_tasks = []
        task_ids_to_remove = []
        for task_id, task_data in list(self._dlq.items()):
            if len(dequeued_tasks) < limit:
                dequeued_tasks.append(task_data)
                task_ids_to_remove.append(task_id)
            else:
                break
        
        for task_id in task_ids_to_remove:
            del self._dlq[task_id]

        logger.debug("Dequeued %d tasks from DLQ.", len(dequeued_tasks))
        return dequeued_tasks

    async def remove(self, task_id: str) -> bool:
        if task_id in self._dlq:
            del self._dlq[task_id]
            logger.info("Task %s removed from DLQ.", task_id)
            return True
        logger.warning("Attempted to remove non-existent task %s from DLQ.", task_id)
        return False

    async def size(self) -> int:
        return len(self._dlq)
