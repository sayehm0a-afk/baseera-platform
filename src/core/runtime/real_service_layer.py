import logging
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RealServiceLayer:
    """Production-grade service layer for coordinating components."""

    def __init__(self, message_bus: Any, task_queue: Any, agent_runtime: Any):
        """Initialize real service layer."""
        self.message_bus = message_bus
        self.task_queue = task_queue
        self.agent_runtime = agent_runtime
        self.is_running = False
        self.start_time = None
        self.request_count = 0
        self.error_count = 0

    async def start(self) -> None:
        """Start the service layer."""
        self.is_running = True
        self.start_time = datetime.now()
        logger.info("Service layer started")

        # Subscribe to message bus events
        self.message_bus.subscribe("agent:task", self._handle_agent_task)
        self.message_bus.subscribe("agent:status", self._handle_agent_status)

    async def stop(self) -> None:
        """Stop the service layer gracefully."""
        logger.info("Service layer stopping...")
        self.is_running = False
        logger.info("Service layer stopped")

    async def submit_task(self, task: Dict[str, Any]) -> bool:
        """Submit a task for processing."""
        try:
            self.request_count += 1

            # Enqueue task
            if self.task_queue.enqueue_task(task):
                logger.info(f"Task submitted: {task.get('task_id', 'unknown')}")

                # Publish event
                self.message_bus.publish("task:submitted", {
                    "task_id": task.get("task_id"),
                    "agent_id": task.get("agent_id"),
                    "timestamp": datetime.now().isoformat(),
                })

                return True
            else:
                logger.error(f"Failed to enqueue task: {task.get('task_id', 'unknown')}")
                self.error_count += 1
                return False

        except Exception as e:
            logger.error(f"Error submitting task: {e}")
            self.error_count += 1
            return False

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a task."""
        try:
            # Query task status from task queue
            queue_length = self.task_queue.get_task_count()
            dead_letter_count = self.task_queue.get_dead_letter_count()

            return {
                "task_id": task_id,
                "queue_length": queue_length,
                "dead_letter_count": dead_letter_count,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return None

    async def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an agent."""
        try:
            return self.agent_runtime.get_agent_status(agent_id)

        except Exception as e:
            logger.error(f"Error getting agent status: {e}")
            return None

    async def get_runtime_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        try:
            uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

            stats = {
                "is_running": self.is_running,
                "uptime_seconds": uptime,
                "request_count": self.request_count,
                "error_count": self.error_count,
            }

            # Add agent runtime stats
            if self.agent_runtime:
                stats.update(self.agent_runtime.get_runtime_stats())

            return stats

        except Exception as e:
            logger.error(f"Error getting runtime stats: {e}")
            return {}

    async def _handle_agent_task(self, task: Dict[str, Any]) -> None:
        """Handle agent task event."""
        try:
            logger.debug(f"Handling agent task event: {task}")
            await self.submit_task(task)
        except Exception as e:
            logger.error(f"Error handling agent task event: {e}")

    async def _handle_agent_status(self, status: Dict[str, Any]) -> None:
        """Handle agent status event."""
        try:
            logger.debug(f"Handling agent status event: {status}")
        except Exception as e:
            logger.error(f"Error handling agent status event: {e}")

    def health_check(self) -> bool:
        """Perform health check on all components."""
        try:
            # Check message bus
            if not self.message_bus.health_check():
                logger.warning("Message bus health check failed")
                return False

            # Check task queue
            if not self.task_queue.health_check():
                logger.warning("Task queue health check failed")
                return False

            logger.debug("Health check passed")
            return True

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return False
