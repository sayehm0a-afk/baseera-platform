import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, Awaitable

logger = logging.getLogger(__name__)

class IMessageBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        raise NotImplementedError

class InMemoryMessageBus(IMessageBus):
    def __init__(self):
        self._subscribers: Dict[str, list[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}
        logger.info("InMemoryMessageBus initialized.")

    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        logger.info(f"[InMemoryMessageBus] Publishing message to topic '{topic}': {message}")
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"[InMemoryMessageBus] Error handling message for topic '{topic}': {e}", exc_info=True)

    async def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        logger.info(f"[InMemoryMessageBus] Subscribing handler to topic '{topic}'")
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
