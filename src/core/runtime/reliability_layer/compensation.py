import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Awaitable

logger = logging.getLogger(__name__)


class ICompensation(ABC):
    """واجهة مجردة للتعويض (Compensation).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ للتعويض.
    """

    @abstractmethod
    async def compensate(
        self,
        operation_id: str,
        compensation_func: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any
    ) -> None:
        """يسجل ويقوم بتشغيل دالة تعويضية لعملية معينة.

        Args:
            operation_id (str): معرف فريد للعملية التي تتطلب التعويض.
            compensation_func (Callable[..., Awaitable[Any]]): الدالة غير المتزامنة التي تمثل إجراء التعويض.
            *args (Any): الوسائط الموضعية لدالة التعويض.
            **kwargs (Any): الوسائط الكلمة الرئيسية لدالة التعويض.
        """
        raise NotImplementedError

    @abstractmethod
    async def run_compensation(self, operation_id: str) -> None:
        """يشغل دالة التعويض المسجلة لعملية معينة.

        Args:
            operation_id (str): معرف العملية التي سيتم تعويضها.
        """
        raise NotImplementedError

    @abstractmethod
    async def clear_compensation(self, operation_id: str) -> None:
        """يمسح دالة التعويض المسجلة لعملية معينة.

        Args:
            operation_id (str): معرف العملية التي سيتم مسح التعويض الخاص بها.
        """
        raise NotImplementedError


class Compensation(ICompensation):
    """تنفيذ التعويض (Compensation).

    مسؤول عن تسجيل وتشغيل الإجراءات التعويضية في حالة فشل العمليات.
    """

    def __init__(self) -> None:
        self._compensations: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._compensation_args: Dict[str, Dict[str, Any]] = {}
        logger.info("Compensation instance created.")

    async def compensate(
        self,
        operation_id: str,
        compensation_func: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any
    ) -> None:
        self._compensations[operation_id] = compensation_func
        self._compensation_args[operation_id] = {"args": args, "kwargs": kwargs}
        logger.info("Compensation function registered for operation %s.", operation_id)

    async def run_compensation(self, operation_id: str) -> None:
        compensation_func = self._compensations.get(operation_id)
        if compensation_func:
            args = self._compensation_args[operation_id].get("args", ())
            kwargs = self._compensation_args[operation_id].get("kwargs", {})
            logger.info("Running compensation for operation %s.", operation_id)
            try:
                await compensation_func(*args, **kwargs)
                logger.info(
                    "Compensation for operation %s completed successfully.",
                    operation_id,
                )
            except Exception as e:
                logger.error(
                    "Compensation for operation %s failed: %s",
                    operation_id,
                    e,
                    exc_info=True,
                )
            finally:
                del self._compensations[operation_id]
                del self._compensation_args[operation_id]
        else:
            logger.warning("No compensation registered for operation %s.", operation_id)

    async def clear_compensation(self, operation_id: str) -> None:
        if operation_id in self._compensations:
            del self._compensations[operation_id]
            del self._compensation_args[operation_id]
            logger.info("Compensation for operation %s cleared.", operation_id)
        else:
            logger.warning("No compensation to clear for operation %s.", operation_id)
