import json
import logging
from typing import Any, Callable, Dict, List, Optional
from redis import Redis

from src.core.config import settings

logger = logging.getLogger(__name__)


class RedisMessageBus:
    """Production-grade message bus using Redis."""

    def __init__(self, host: str = None, port: int = None, db: int = 0, password: str = None):
        """Initialize Redis message bus.

        With no explicit host/port/password (the production path), the
        connection string is built from `settings.redis_dsn` -- the one
        place "prefer REDIS_URL, else assemble from host/port/password"
        is decided (see Settings.redis_dsn) -- instead of independently
        reading REDIS_HOST/REDIS_PORT via os.getenv and silently
        defaulting to localhost, which never picks up a managed Redis
        provider's REDIS_URL (the bug that made this bus fail to
        connect on Railway, where only REDIS_URL is injected).
        Explicit host/port/password (e.g. from a test) still take
        priority when given.
        """
        if host or port or password:
            auth = f":{password}@" if password else ""
            self._dsn = f"redis://{auth}{host or 'localhost'}:{port or 6379}/{db}"
        else:
            self._dsn = settings.redis_dsn
        self.connection_pool = None
        self.redis_client = None
        self.subscribers: Dict[str, List[Callable]] = {}
        self._connect()

    def _connect(self):
        """Establish connection to Redis."""
        try:
            self.redis_client = Redis.from_url(
                self._dsn,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            self.connection_pool = self.redis_client.connection_pool
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis message bus.")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a topic."""
        try:
            message_json = json.dumps(message)
            result = self.redis_client.publish(topic, message_json)
            logger.debug(f"Published message to topic '{topic}': {result} subscribers")
            return result > 0
        except Exception as e:
            logger.error(f"Failed to publish message to topic '{topic}': {e}")
            return False

    def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to a topic with a handler."""
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(handler)
        logger.debug(f"Subscribed to topic '{topic}'")

    def unsubscribe(self, topic: str, handler: Callable) -> None:
        """Unsubscribe from a topic."""
        if topic in self.subscribers:
            self.subscribers[topic] = [h for h in self.subscribers[topic] if h != handler]
            logger.debug(f"Unsubscribed from topic '{topic}'")

    def enqueue_task(self, queue_name: str, task: Dict[str, Any]) -> bool:
        """Enqueue a task to a queue."""
        try:
            task_json = json.dumps(task)
            self.redis_client.rpush(queue_name, task_json)
            logger.debug(f"Enqueued task to queue '{queue_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task to queue '{queue_name}': {e}")
            return False

    def dequeue_task(self, queue_name: str, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Dequeue a task from a queue."""
        try:
            task_json = self.redis_client.blpop(queue_name, timeout=timeout)
            if task_json:
                return json.loads(task_json[1])
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue task from queue '{queue_name}': {e}")
            return None

    def get_queue_length(self, queue_name: str) -> int:
        """Get the length of a queue."""
        try:
            return self.redis_client.llen(queue_name)
        except Exception as e:
            logger.error(f"Failed to get queue length for '{queue_name}': {e}")
            return 0

    def clear_queue(self, queue_name: str) -> bool:
        """Clear all tasks from a queue."""
        try:
            self.redis_client.delete(queue_name)
            logger.info(f"Cleared queue '{queue_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue '{queue_name}': {e}")
            return False

    def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def close(self):
        """Close Redis connection."""
        try:
            if self.connection_pool:
                self.connection_pool.disconnect()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
