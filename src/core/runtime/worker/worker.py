import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, Awaitable

logger = logging.getLogger(__name__)


class IWorker(ABC):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError


class Worker(IWorker):
    def __init__(self, worker_id: str, task_queue: Any, handler: Callable[[Dict[str, Any]], Awaitable[None]]):
        self._worker_id = worker_id
        self._task_queue = task_queue
        self._handler = handler
        self._running = False
        self._task: asyncio.Task = None
        logger.info(f"Worker \'{self._worker_id}\' initialized.")

    async def start(self) -> None:
        if self._running:
            logger.warning(f"Worker \'{self._worker_id}\' is already running.")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_worker())
        logger.info(f"Worker \'{self._worker_id}\' started.")

    async def stop(self) -> None:
        if not self._running:
            logger.warning(f"Worker \'{self._worker_id}\' is not running.")
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.info(f"Worker \'{self._worker_id}\' task cancelled.")
        logger.info(f"Worker \'{self._worker_id}\' stopped.")

    async def _run_worker(self) -> None:
        logger.info(f"Worker \'{self._worker_id}\' is processing tasks.")
        while self._running:
            try:
                task_data = await self._task_queue.get_task(self._worker_id)
                if task_data:
                    task_id = task_data["task_id"]
                    handler_id = task_data["task_payload"]["handler_id"]
                    task_payload = task_data["task_payload"]["payload"]
                    handler = self._task_queue._handlers.get(handler_id)

                    if handler:
                        await self._task_queue._execute_task(task_id, task_payload, handler)
                    else:
                        logger.error(f"Handler for task {task_id} not found in TaskQueue.")
                else:
                    await asyncio.sleep(0.1)  # Prevent busy-waiting
            except asyncio.CancelledError:
                logger.info(f"Worker {self._worker_id} processing loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in Worker {self._worker_id} processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Wait before retrying loop
