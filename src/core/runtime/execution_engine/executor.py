import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Awaitable

logger = logging.getLogger(__name__)

class IExecutor(ABC):
    """واجهة مجردة للمنفذ (Executor).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ للمنفذ.
    """

    @abstractmethod
    async def execute_task(self, task_id: str, task_function: Callable[..., Awaitable[Any]], **kwargs: Any) -> Any:
        """ينفذ مهمة معينة.

        Args:
            task_id (str): معرف فريد للمهمة.
            task_function (Callable[..., Awaitable[Any]]): الدالة غير المتزامنة التي تمثل المهمة.
            **kwargs (Any): الوسائط التي سيتم تمريرها إلى دالة المهمة.

        Returns:
            Any: نتيجة تنفيذ المهمة.

        Raises:
            Exception: إذا فشل تنفيذ المهمة.
        """
        raise NotImplementedError


class Executor(IExecutor):
    """تنفيذ المنفذ (Executor).

    مسؤول عن تنفيذ المهام الفردية.
    """

    def __init__(self) -> None:
        logger.info("Executor instance created.")

    async def execute_task(self, task_id: str, task_function: Callable[..., Awaitable[Any]], **kwargs: Any) -> Any:
        logger.info("Executing task %s with function %s and kwargs %s", task_id, task_function.__name__, kwargs)
        try:
            result = await task_function(**kwargs)
            logger.info("Task %s completed successfully.", task_id)
            return result
        except Exception as e:
            logger.error("Task %s failed: %s", task_id, e, exc_info=True)
            raise
