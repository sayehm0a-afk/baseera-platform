import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Awaitable

from core.runtime.reliability_layer.circuit_breaker import ICircuitBreaker, CircuitBreaker, CircuitBreakerOpenError
from core.runtime.reliability_layer.failure_recovery import IFailureRecovery, FailureRecovery
from core.runtime.reliability_layer.compensation import ICompensation, Compensation

logger = logging.getLogger(__name__)

class IReliabilityLayer(ABC):
    """واجهة مجردة لطبقة الموثوقية (Reliability Layer).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لطبقة الموثوقية.
    """

    @abstractmethod
    async def execute_reliable(self, func: Callable[..., Awaitable[Any]], 
                                 fallback_func: Optional[Callable[..., Awaitable[Any]]] = None,
                                 compensation_func: Optional[Callable[..., Awaitable[Any]]] = None,
                                 operation_id: Optional[str] = None,
                                 use_circuit_breaker: bool = True,
                                 *args: Any, **kwargs: Any) -> Any:
        """ينفذ دالة مع تطبيق آليات الموثوقية (قاطع الدائرة، استعادة الفشل، التعويض).

        Args:
            func (Callable[..., Awaitable[Any]]): الدالة المراد تنفيذها.
            fallback_func (Optional[Callable[..., Awaitable[Any]]]): دالة احتياطية يتم استدعاؤها في حالة فشل الدالة الأصلية.
            compensation_func (Optional[Callable[..., Awaitable[Any]]]): دالة تعويضية يتم استدعاؤها في حالة فشل الدالة الأصلية بعد محاولات إعادة المحاولة.
            operation_id (Optional[str]): معرف فريد للعملية، يستخدم لتسجيل التعويض.
            use_circuit_breaker (bool): ما إذا كان سيتم استخدام قاطع الدائرة لهذه العملية.
            *args (Any): الوسائط الموضعية للدالة.
            **kwargs (Any): الوسائط الكلمة الرئيسية للدالة.

        Returns:
            Any: نتيجة تنفيذ الدالة الأصلية أو الدالة الاحتياطية.

        Raises:
            Exception: إذا فشلت جميع آليات الموثوقية.
        """
        raise NotImplementedError


class ReliabilityLayer(IReliabilityLayer):
    """تنفيذ طبقة الموثوقية (Reliability Layer).

    تجمع بين قاطع الدائرة واستعادة الفشل والتعويض لتوفير تنفيذ موثوق للعمليات.
    """

    def __init__(self, 
                 circuit_breaker: Optional[ICircuitBreaker] = None,
                 failure_recovery: Optional[IFailureRecovery] = None,
                 compensation: Optional[ICompensation] = None) -> None:
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._failure_recovery = failure_recovery or FailureRecovery()
        self._compensation = compensation or Compensation()
        logger.info("ReliabilityLayer instance created.")

    async def execute_reliable(self, func: Callable[..., Awaitable[Any]], 
                                 fallback_func: Optional[Callable[..., Awaitable[Any]]] = None,
                                 compensation_func: Optional[Callable[..., Awaitable[Any]]] = None,
                                 operation_id: Optional[str] = None,
                                 use_circuit_breaker: bool = True,
                                 *args: Any, **kwargs: Any) -> Any:
        
        # Register compensation if provided and operation_id is present
        if compensation_func and operation_id:
            await self._compensation.compensate(operation_id, compensation_func, *args, **kwargs)

        try:
            if use_circuit_breaker:
                # Execute with circuit breaker
                result = await self._circuit_breaker.execute(func, *args, **kwargs)
            else:
                # Execute directly if circuit breaker is not used
                result = await func(*args, **kwargs)
            
            # If successful, clear any registered compensation for this operation
            if operation_id:
                await self._compensation.clear_compensation(operation_id)
            return result

        except CircuitBreakerOpenError:
            logger.warning("Circuit breaker is open for operation. Attempting fallback or re-raising.")
            # If circuit breaker is open, try fallback directly
            if fallback_func:
                try:
                    fallback_result = await fallback_func(*args, **kwargs)
                    return fallback_result
                except Exception as fb_e:
                    logger.error("Fallback function also failed after circuit breaker open: %s", fb_e, exc_info=True)
                    # If fallback fails, and compensation was registered, run it
                    if operation_id:
                        await self._compensation.run_compensation(operation_id)
                    raise fb_e
            else:
                # No fallback, and circuit breaker is open, so re-raise
                if operation_id:
                    await self._compensation.run_compensation(operation_id)
                raise

        except Exception as e:
            logger.error("Operation failed. Attempting failure recovery: %s", e, exc_info=True)
            # If any other exception occurs, use failure recovery logic
            try:
                result = await self._failure_recovery.execute_with_recovery(func, fallback_func, compensation_func, *args, **kwargs)
                return result
            except Exception as recovery_e:
                logger.error("Failure recovery also failed: %s", recovery_e, exc_info=True)
                # If failure recovery fails, and compensation was registered, run it
                if operation_id:
                    await self._compensation.run_compensation(operation_id)
                raise recovery_e
