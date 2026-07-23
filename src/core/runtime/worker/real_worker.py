import asyncio
import logging
import signal
from typing import Any, Callable, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class RealWorker:
    """Production-grade worker for processing tasks."""

    def __init__(self, worker_id: str, task_queue: Any, max_retries: int = 3):
        """Initialize real worker."""
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.max_retries = max_retries
        self.is_running = False
        self.processed_count = 0
        self.failed_count = 0
        self.start_time = None
        self.handlers: Dict[str, Callable] = {}

    def register_handler(self, task_type: str, handler: Callable) -> None:
        """Register a handler for a specific task type."""
        self.handlers[task_type] = handler
        logger.info(f"Worker {self.worker_id} registered handler for task type '{task_type}'")

    async def start(self) -> None:
        """Start the worker."""
        self.is_running = True
        self.start_time = datetime.now()
        logger.info(f"Worker {self.worker_id} started")

        # Handle graceful shutdown
        def signal_handler(sig, frame):
            logger.info(f"Worker {self.worker_id} received shutdown signal")
            self.is_running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        while self.is_running:
            try:
                # Dequeue task
                task = self.task_queue.dequeue_task()

                if task:
                    await self._process_task(task)
                else:
                    # No task available, wait before retrying
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                await asyncio.sleep(5)

    async def _process_task(self, task: Dict[str, Any]) -> None:
        """Process a single task."""
        task_id = task.get("task_id", "unknown")
        task_type = task.get("task_type", "unknown")

        logger.info(f"Worker {self.worker_id} processing task {task_id} (type: {task_type})")

        # Get handler for task type
        handler = self.handlers.get(task_type)
        if not handler:
            logger.error(f"No handler registered for task type '{task_type}'")
            self.task_queue.move_to_dead_letter(task, f"No handler for task type '{task_type}'")
            self.failed_count += 1
            return

        # Process task with retries
        retries = 0
        while retries < self.max_retries:
            try:
                # Execute handler
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(task)
                else:
                    result = handler(task)

                logger.info(f"Worker {self.worker_id} completed task {task_id}")
                self.processed_count += 1
                return

            except Exception as e:
                retries += 1
                logger.warning(f"Worker {self.worker_id} failed to process task {task_id} (attempt {retries}/{self.max_retries}): {e}")

                if retries < self.max_retries:
                    # Exponential backoff
                    wait_time = 2 ** retries
                    await asyncio.sleep(wait_time)
                else:
                    # Move to dead letter queue after max retries
                    self.task_queue.move_to_dead_letter(task, f"Failed after {self.max_retries} retries: {str(e)}")
                    self.failed_count += 1

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info(f"Worker {self.worker_id} stopping...")
        self.is_running = False

        # Wait for current task to complete
        max_wait = 30
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

        logger.info(f"Worker {self.worker_id} stopped. Processed: {self.processed_count}, Failed: {self.failed_count}")

    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return {
            "worker_id": self.worker_id,
            "is_running": self.is_running,
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "uptime_seconds": uptime,
            "queue_length": self.task_queue.get_task_count(),
            "dead_letter_count": self.task_queue.get_dead_letter_count(),
        }
