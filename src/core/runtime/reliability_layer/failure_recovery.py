import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

class IFailureRecovery(ABC):
    """واجهة مجردة لاستعادة الفشل (Failure Recovery).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لاستعادة الفشل.
    """

    @abstractmethod
    async def execute_with_recovery(self, func: Callable[..., Any], fallback_func: Optional[Callable[..., Any]] = None,
                                    compensation_func: Optional[Callable[..., Any]] = None, *args: Any, **kwargs: Any) -> Any:
        """ينفذ دالة مع آليات استعادة الفشل.

        Args:
            func (Callable[..., Any]): الدالة المراد تنفيذها.
            fallback_func (Optional[Callable[..., Any]]): دالة احتياطية يتم استدعاؤها في حالة فشل الدالة الأصلية.
            compensation_func (Optional[Callable[..., Any]]): دالة تعويضية يتم استدعاؤها في حالة فشل الدالة الأصلية بعد محاولات إعادة المحاولة.
            *args (Any): الوسائط الموضعية للدالة.
            **kwargs (Any): الوسائط الكلمة الرئيسية للدالة.

        Returns:
            Any: نتيجة تنفيذ الدالة الأصلية أو الدالة الاحتياطية.

        Raises:
            Exception: إذا فشلت الدالة الأصلية والدالة الاحتياطية (إذا كانت موجودة).
        """
        raise NotImplementedError


class FailureRecovery(IFailureRecovery):
    """تنفيذ استعادة الفشل (Failure Recovery).

    يوفر آليات للتعامل مع فشل العمليات، مثل الدوال الاحتياطية والتعويض.
    """

    def __init__(self) -> None:
        logger.info("FailureRecovery instance created.")

    async def execute_with_recovery(self, func: Callable[..., Any], fallback_func: Optional[Callable[..., Any]] = None,
                                    compensation_func: Optional[Callable[..., Any]] = None, *args: Any, **kwargs: Any) -> Any:
        try:
            result = await func(*args, **kwargs)
            logger.info("Function %s executed successfully.", func.__name__)
            return result
        except Exception as e:
            logger.error("Function %s failed: %s", func.__name__, e, exc_info=True)
            if fallback_func:
                logger.info("Attempting to execute fallback function %s.", fallback_func.__name__)
                try:
                    fallback_result = await fallback_func(*args, **kwargs)
                    logger.info("Fallback function %s executed successfully.", fallback_func.__name__)
                    return fallback_result
                except Exception as fb_e:
                    logger.error("Fallback function %s also failed: %s", fallback_func.__name__, fb_e, exc_info=True)
                    if compensation_func:
                        logger.info("Attempting to execute compensation function %s.", compensation_func.__name__)
                        try:
                            await compensation_func(*args, **kwargs)
                            logger.info("Compensation function %s executed successfully.", compensation_func.__name__)
                        except Exception as comp_e:
                            logger.error("Compensation function %s also failed: %s", compensation_func.__name__, comp_e, exc_info=True)
                    raise fb_e # Re-raise fallback exception if compensation also fails or is not present
            elif compensation_func:
                logger.info("Attempting to execute compensation function %s as no fallback was provided.", compensation_func.__name__)
                try:
                    await compensation_func(*args, **kwargs)
                    logger.info("Compensation function %s executed successfully.", compensation_func.__name__)
                except Exception as comp_e:
                    logger.error("Compensation function %s also failed: %s", compensation_func.__name__, comp_e, exc_info=True)
                raise e # Re-raise original exception if compensation fails or is not present
            else:
                raise e # Re-raise original exception if no fallback or compensation is provided
