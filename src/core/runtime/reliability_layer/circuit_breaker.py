import logging
import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Any
import time

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ICircuitBreaker(ABC):
    """واجهة مجردة لقاطع الدائرة (Circuit Breaker).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لقاطع الدائرة.
    """

    @abstractmethod
    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """ينفذ دالة محمية بواسطة قاطع الدائرة.

        Args:
            func (Callable[..., Any]): الدالة المراد تنفيذها.
            *args (Any): الوسائط الموضعية للدالة.
            **kwargs (Any): الوسائط الكلمة الرئيسية للدالة.

        Returns:
            Any: نتيجة تنفيذ الدالة.

        Raises:
            CircuitBreakerOpenError: إذا كان قاطع الدائرة مفتوحًا.
            Exception: إذا فشلت الدالة لأسباب أخرى.
        """
        raise NotImplementedError


class CircuitBreakerOpenError(Exception):
    """استثناء يتم رفعه عندما يكون قاطع الدائرة مفتوحًا."""

    pass


class CircuitBreaker(ICircuitBreaker):
    """تنفيذ قاطع الدائرة (Circuit Breaker).

    يحمي العمليات من الفشل المتكرر عن طريق فتح الدائرة مؤقتًا.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 5,  # seconds
        expected_successes: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._expected_successes = expected_successes

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._success_count = 0
        self._lock = asyncio.Lock()

        logger.info(
            "CircuitBreaker instance created with failure_threshold=%d, recovery_timeout=%d, expected_successes=%d.",
            failure_threshold,
            recovery_timeout,
            expected_successes,
        )

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    async def _transition_to_open(self) -> None:
        # Assumes lock is already held by the caller
        if self._state != CircuitBreakerState.OPEN:
            self._state = CircuitBreakerState.OPEN
            self._last_failure_time = time.monotonic()
            logger.warning("Circuit Breaker transitioned to OPEN state.")

    async def _transition_to_half_open(self) -> None:
        # Assumes lock is already held by the caller
        if self._state != CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.HALF_OPEN
            self._success_count = 0
            logger.info("Circuit Breaker transitioned to HALF-OPEN state.")

    async def _transition_to_closed(self) -> None:
        # Assumes lock is already held by the caller
        if self._state != CircuitBreakerState.CLOSED:
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            logger.info("Circuit Breaker transitioned to CLOSED state.")

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        current_state = CircuitBreakerState.CLOSED
        async with self._lock:
            current_state = self._state
            if current_state == CircuitBreakerState.OPEN:
                if (
                    time.monotonic() - self._last_failure_time
                ) > self._recovery_timeout:
                    await self._transition_to_half_open()
                    current_state = self._state  # Update current_state after transition
                else:
                    logger.warning("Circuit Breaker is OPEN. Operation prevented.")
                    raise CircuitBreakerOpenError("Circuit Breaker is OPEN")

        if current_state == CircuitBreakerState.HALF_OPEN:
            try:
                result = await func(*args, **kwargs)
                async with self._lock:
                    self._success_count += 1
                    if self._success_count >= self._expected_successes:
                        await self._transition_to_closed()
                return result
            except Exception as e:
                logger.error("Circuit breaker operation failed in HALF-OPEN state: %s", e, exc_info=True)
                async with self._lock:
                    self._failure_count += 1  # In HALF-OPEN, any failure opens it again
                    await self._transition_to_open()
                raise

        # State is CLOSED (or was HALF_OPEN and transitioned to CLOSED)
        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._failure_count = 0  # Reset failure count on success
            return result
        except Exception as e:
            logger.error("Circuit breaker operation failed in CLOSED state: %s", e, exc_info=True)
            async with self._lock:
                self._failure_count += 1
                logger.warning(
                    "Operation failed. Failure count: %d/%d",
                    self._failure_count,
                    self._failure_threshold,
                )
                if self._failure_count >= self._failure_threshold:
                    await self._transition_to_open()
            raise
