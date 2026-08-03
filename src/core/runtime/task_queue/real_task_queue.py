import json
import logging
from typing import Any, Dict, Optional
import redis

from src.core.config import settings

logger = logging.getLogger(__name__)


class RealTaskQueue:
    """Production-grade task queue using Redis."""

    def __init__(self, host: str = None, port: int = None, db: int = 0, password: str = None):
        """Initialize real task queue.

        Same fix and reasoning as RedisMessageBus.__init__: with no
        explicit host/port/password, the connection string comes from
        `settings.redis_dsn` (prefers REDIS_URL, the only variable a
        managed Redis provider like Railway actually injects) instead
        of independently reading REDIS_HOST/REDIS_PORT and defaulting
        to localhost.
        """
        if host or port or password:
            auth = f":{password}@" if password else ""
            self._dsn = f"redis://{auth}{host or 'localhost'}:{port or 6379}/{db}"
        else:
            self._dsn = settings.redis_dsn
        self.redis_client = None
        self.queue_name = "basirah:tasks"
        self.dead_letter_queue_name = "basirah:tasks:dead_letter"
        self._connect()

    def _connect(self):
        """Establish connection to Redis."""
        try:
            self.redis_client = redis.Redis.from_url(
                self._dsn,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis task queue.")
        except Exception as e:
            logger.error(f"Failed to connect to Redis task queue: {e}")
            raise

    def enqueue_task(self, task: Dict[str, Any], priority: int = 0) -> bool:
        """Enqueue a task to the task queue."""
        try:
            task_json = json.dumps(task)
            # Use sorted set for priority queue
            score = -priority  # Negative for descending order (higher priority = lower score)
            self.redis_client.zadd(self.queue_name, {task_json: score})
            logger.debug(f"Enqueued task with priority {priority}: {task.get('task_id', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return False

    def dequeue_task(self) -> Optional[Dict[str, Any]]:
        """Dequeue a task from the task queue."""
        try:
            # Get task with highest priority (lowest score)
            tasks = self.redis_client.zrange(self.queue_name, 0, 0, withscores=False)
            if tasks:
                task_json = tasks[0]
                self.redis_client.zrem(self.queue_name, task_json)
                return json.loads(task_json)
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue task: {e}")
            return None

    def get_task_count(self) -> int:
        """Get the number of tasks in the queue."""
        try:
            return self.redis_client.zcard(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get task count: {e}")
            return 0

    def move_to_dead_letter(self, task: Dict[str, Any], reason: str) -> bool:
        """Move a task to the dead letter queue."""
        try:
            task["dead_letter_reason"] = reason
            task_json = json.dumps(task)
            self.redis_client.rpush(self.dead_letter_queue_name, task_json)
            logger.warning(f"Moved task to dead letter queue: {task.get('task_id', 'unknown')} - {reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to move task to dead letter queue: {e}")
            return False

    def get_dead_letter_count(self) -> int:
        """Get the number of tasks in the dead letter queue."""
        try:
            return self.redis_client.llen(self.dead_letter_queue_name)
        except Exception as e:
            logger.error(f"Failed to get dead letter queue count: {e}")
            return 0

    def clear_queue(self) -> bool:
        """Clear all tasks from the queue."""
        try:
            self.redis_client.delete(self.queue_name)
            logger.info("Cleared task queue")
            return True
        except Exception as e:
            logger.error(f"Failed to clear task queue: {e}")
            return False

    def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Task queue health check failed: {e}")
            return False

    def close(self):
        """Close Redis connection."""
        try:
            if self.redis_client:
                self.redis_client.close()
            logger.info("Task queue connection closed")
        except Exception as e:
            logger.error(f"Error closing task queue connection: {e}")
