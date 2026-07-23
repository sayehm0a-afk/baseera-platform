import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DependencyContainer:
    """Production-grade dependency injection container."""

    def __init__(self):
        """Initialize dependency container."""
        self._services: Dict[str, Any] = {}
        self._singletons: Dict[str, Any] = {}

    def register_service(self, name: str, factory: callable, singleton: bool = False) -> None:
        """Register a service with the container."""
        self._services[name] = {
            "factory": factory,
            "singleton": singleton,
        }
        logger.debug(f"Registered service: {name} (singleton: {singleton})")

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a service instance with the container."""
        self._singletons[name] = instance
        logger.debug(f"Registered instance: {name}")

    def get_service(self, name: str) -> Optional[Any]:
        """Get a service from the container."""
        try:
            # Check if instance exists in singletons
            if name in self._singletons:
                return self._singletons[name]

            # Check if service is registered
            if name not in self._services:
                logger.warning(f"Service not found: {name}")
                return None

            service_info = self._services[name]
            factory = service_info["factory"]

            # Create service instance
            instance = factory()

            # Store singleton if configured
            if service_info["singleton"]:
                self._singletons[name] = instance

            return instance

        except Exception as e:
            logger.error(f"Error getting service {name}: {e}")
            return None

    def clear(self) -> None:
        """Clear all services and instances."""
        self._services.clear()
        self._singletons.clear()
        logger.debug("Dependency container cleared")


# Global dependency container
_container = DependencyContainer()


def get_container() -> DependencyContainer:
    """Get the global dependency container."""
    return _container


def setup_production_dependencies() -> DependencyContainer:
    """Setup production dependencies."""
    from src.core.db.database import get_session, get_session_factory, get_engine
    from src.core.messaging.redis_message_bus import RedisMessageBus
    from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
    from src.core.runtime.real_agent_runtime import RealAgentRuntime
    from src.core.runtime.real_service_layer import RealServiceLayer

    container = get_container()

    try:
        # Register database (get_engine()/get_session_factory() initialize the
        # engine here, at explicit startup time, not as an import side effect)
        container.register_instance("db_engine", get_engine())
        container.register_instance("db_session_factory", get_session_factory())
        container.register_service("db_session", get_session, singleton=False)

        # Register message bus
        def create_message_bus():
            return RedisMessageBus(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
            )
        container.register_service("message_bus", create_message_bus, singleton=True)

        # Register task queue
        def create_task_queue():
            return RealTaskQueue(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
            )
        container.register_service("task_queue", create_task_queue, singleton=True)

        # Register agent runtime
        def create_agent_runtime():
            message_bus = container.get_service("message_bus")
            task_queue = container.get_service("task_queue")
            return RealAgentRuntime(message_bus, task_queue)
        container.register_service("agent_runtime", create_agent_runtime, singleton=True)

        # Register service layer
        def create_service_layer():
            message_bus = container.get_service("message_bus")
            task_queue = container.get_service("task_queue")
            agent_runtime = container.get_service("agent_runtime")
            return RealServiceLayer(message_bus, task_queue, agent_runtime)
        container.register_service("service_layer", create_service_layer, singleton=True)

        logger.info("Production dependencies setup completed")
        return container

    except Exception as e:
        logger.error(f"Error setting up production dependencies: {e}")
        raise
