import json
import logging
import os
from typing import Any, Callable, Dict, Optional
import redis
from redis import Redis

logger = logging.getLogger(__name__)

class RealTaskQueue:
    """Production-grade task queue using Redis."""
    
    def __init__(self, host: str = None, port: int = None, db: int = 0):
        """Initialize real task queue."""
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", 6379))
        self.db = db
        self.redis_client = None
        self.queue_name = "basirah:tasks"
        self.dead_letter_queue_name = "basirah:tasks:dead_letter"
        self._connect()
    
    def _connect(self):
        """Establish connection to Redis."""
        try:
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis task queue at {self.host}:{self.port}")
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
