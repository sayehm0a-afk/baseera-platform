import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class IScheduler(ABC):
    """واجهة مجردة للمجدول (Scheduler).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ للمجدول.
    """

    @abstractmethod
    async def schedule_task(self, task_id: str, task_payload: Dict[str, Any], delay_seconds: int = 0, priority: int = 0) -> None:
        """يجدول مهمة للتنفيذ.

        Args:
            task_id (str): معرف فريد للمهمة.
            task_payload (Dict[str, Any]): حمولة (بيانات) المهمة.
            delay_seconds (int): التأخير قبل تنفيذ المهمة بالثواني (افتراضي 0).
            priority (int): أولوية المهمة (افتراضي 0، حيث الأرقام الأعلى تعني أولوية أعلى).
        """
        raise NotImplementedError

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """يلغي مهمة مجدولة.

        Args:
            task_id (str): معرف المهمة المراد إلغاؤها.

        Returns:
            bool: True إذا تم إلغاء المهمة بنجاح، False بخلاف ذلك.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_scheduled_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """يسترد قائمة بالمهام المجدولة.

        Args:
            limit (int): الحد الأقصى لعدد المهام المراد استردادها.

        Returns:
            List[Dict[str, Any]]: قائمة بالمهام المجدولة.
        """
        raise NotImplementedError


class Scheduler(IScheduler):
    """تنفيذ المجدول (Scheduler).

    مسؤول عن جدولة المهام وإلغائها واستردادها.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Dict[str, Any]] = {}
        logger.info("Scheduler instance created.")

    async def schedule_task(self, task_id: str, task_payload: Dict[str, Any], delay_seconds: int = 0, priority: int = 0) -> None:
        if task_id in self._tasks:
            logger.warning("Task %s already scheduled. Overwriting.", task_id)
        
        self._tasks[task_id] = {
            "task_id": task_id,
            "task_payload": task_payload,
            "delay_seconds": delay_seconds,
            "priority": priority,
            "status": "scheduled"
        }
        logger.info("Task %s scheduled with delay %d seconds and priority %d.", task_id, delay_seconds, priority)

    async def cancel_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info("Task %s cancelled.", task_id)
            return True
        logger.warning("Attempted to cancel non-existent task %s.", task_id)
        return False

    async def get_scheduled_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        # For simplicity, return all tasks for now. In a real implementation, this would involve sorting by schedule time and priority.
        return list(self._tasks.values())[:limit]
