import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from src.core.runtime.task_queue.scheduler import IScheduler, Scheduler
from src.core.runtime.task_queue.priority_queue import IPriorityQueue, PriorityQueue
from src.core.runtime.task_queue.retry_policy import (
    IRetryPolicy,
    ExponentialBackoffRetryPolicy,
)
from src.core.runtime.task_queue.dead_letter_queue import IDeadLetterQueue, DeadLetterQueue

logger = logging.getLogger(__name__)


class ITaskQueue(ABC):
    """واجهة مجردة لقائمة المهام (Task Queue).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لقائمة المهام.
    """

    @abstractmethod
    async def enqueue_task(
        self,
        task_id: str,
        task_payload: Dict[str, Any],
        handler: Callable,
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> None:
        """يضيف مهمة إلى قائمة الانتظار للمعالجة.

        Args:
            task_id (str): معرف فريد للمهمة.
            task_payload (Dict[str, Any]): حمولة (بيانات) المهمة.
            handler (Callable): الدالة التي ستعالج المهمة.
            delay_seconds (int): التأخير قبل تنفيذ المهمة بالثواني (افتراضي 0).
            priority (int): أولوية المهمة (افتراضي 0، حيث الأرقام الأعلى
                تعني أولوية أعلى).
        """
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        """يبدأ معالجة المهام في قائمة الانتظار."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """يوقف معالجة المهام في قائمة الانتظار."""
        raise NotImplementedError

    @abstractmethod
    async def get_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """يجلب مهمة للعامل لمعالجتها.

        Args:
            worker_id (str): معرف العامل الذي يطلب المهمة.

        Returns:
            Optional[Dict[str, Any]]: المهمة التي سيتم معالجتها، أو None إذا لم تكن هناك مهام متاحة.
        """
        raise NotImplementedError


class TaskQueue(ITaskQueue):
    """تنفيذ قائمة المهام (Task Queue).

    يدير جدولة المهام، والأولوية، وإعادة المحاولة، وقائمة انتظار الرسائل
    الميتة.
    """

    def __init__(
        self,
        scheduler: Optional[IScheduler] = None,
        priority_queue: Optional[IPriorityQueue] = None,
        retry_policy: Optional[IRetryPolicy] = None,
        dead_letter_queue: Optional[IDeadLetterQueue] = None,
    ) -> None:
        self._scheduler = scheduler or Scheduler()
        self._priority_queue = priority_queue or PriorityQueue()
        self._retry_policy = retry_policy or ExponentialBackoffRetryPolicy()
        self._dead_letter_queue = dead_letter_queue or DeadLetterQueue()
        self._handlers: Dict[str, Callable] = {}
        self._processing_task: Optional[asyncio.Task] = None
        self._worker_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        logger.info("TaskQueue instance created.")

    async def enqueue_task(
        self,
        task_id: str,
        task_payload: Dict[str, Any],
        handler: Callable,
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> None:
        self._handlers[task_id] = handler
        await self._scheduler.schedule_task(
            task_id,
            {"payload": task_payload, "handler_id": task_id},
            delay_seconds,
            priority,
        )
        logger.info(
            "Task %s enqueued with delay %d and priority %d.",
            task_id,
            delay_seconds,
            priority,
        )

    async def start(self) -> None:
        if self._running:
            logger.warning("TaskQueue is already running.")
            return
        self._running = True
        # TaskQueue no longer processes tasks directly, workers will pull them.
        # We still need to manage scheduled tasks moving to priority queue.
        self._processing_task = asyncio.create_task(self._move_scheduled_to_priority_queue())
        logger.info("TaskQueue started processing tasks.")

    async def stop(self) -> None:
        if not self._running:
            logger.warning("TaskQueue is not running.")
            return
        self._running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                logger.info("TaskQueue processing task cancelled.")
        logger.info("TaskQueue stopped processing tasks.")

    async def _move_scheduled_to_priority_queue(self) -> None:
        while self._running:
            try:
                # In a real scenario, this would involve fetching from
                # scheduler
                # based on delay
                # For now, we\\\'ll just simulate by taking from
                # scheduler and
                # putting
                # into priority queue
                scheduled_tasks = await self._scheduler.get_scheduled_tasks(limit=1)
                if scheduled_tasks:
                    task_data = scheduled_tasks[0]
                    task_id = task_data["task_id"]
                    # Remove from scheduler once picked up for processing
                    await self._scheduler.cancel_task(task_id)
                    await self._priority_queue.put(
                        task_data, priority=task_data["priority"]
                    )
                    logger.debug(
                        "Moved task %s from scheduler to priority queue.", task_id
                    )

                await asyncio.sleep(0.1)  # Prevent busy-waiting
            except asyncio.CancelledError:
                logger.info("TaskQueue processing loop cancelled.")
                break
            except Exception as e:
                logger.error("Error in TaskQueue processing loop: %s", e, exc_info=True)
                await asyncio.sleep(1)  # Wait before retrying loop

    async def get_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """يجلب مهمة للعامل لمعالجتها."""
        if not await self._priority_queue.empty():
            task_to_process = await self._priority_queue.get()
            task_id = task_to_process["task_id"]
            handler_id = task_to_process["task_payload"]["handler_id"]
            task_payload = task_to_process["task_payload"]["payload"]
            handler = self._handlers.get(handler_id)

            if not handler:
                logger.error(
                    "Handler for task %s not found. Moving to DLQ.", task_id
                )
                await self._dead_letter_queue.enqueue(
                    task_id, task_payload, "Handler not found"
                )
                return None  # Return None if handler not found, so worker doesn't try to execute

            logger.debug("Worker %s fetched task %s from priority queue.", worker_id, task_id)
            return {"task_id": task_id, "task_payload": task_payload, "handler": handler}
        return None

    async def _execute_task(
        self,
        task_id: str,
        task_payload: Dict[str, Any],
        handler: Callable,
        attempt_count: int = 1,
    ) -> None:
        try:
            logger.info("Executing task %s (attempt %d).", task_id, attempt_count)
            await handler(task_payload)
            logger.info("Task %s completed successfully.", task_id)
        except Exception as e:
            logger.error(
                "Task %s failed (attempt %d): %s",
                task_id,
                attempt_count,
                e,
                exc_info=True,
            )
            if await self._retry_policy.should_retry(task_id, attempt_count, e):
                delay = await self._retry_policy.get_delay_seconds(
                    task_id, attempt_count
                )
                logger.info("Retrying task %s in %d seconds.", task_id, delay)
                # Re-enqueue with delay and increment attempt count
                await self._scheduler.schedule_task(
                    task_id,
                    {
                        "payload": task_payload,
                        "handler_id": task_id,
                        "attempt_count": attempt_count + 1,
                    },
                    delay,
                    task_payload.get("priority", 0),
                )
            else:
                logger.error(
                    "Task %s failed after %d attempts. Moving to DLQ.",
                    task_id,
                    attempt_count,
                )
                await self._dead_letter_queue.enqueue(task_id, task_payload, str(e))
