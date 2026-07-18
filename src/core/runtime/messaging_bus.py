import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Type, Union

logger = logging.getLogger(__name__)

class IMessagingBus(ABC):
    """واجهة مجردة لـ Messaging Bus.

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لـ Messaging Bus.
    """

    @abstractmethod
    async def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """ينشر حدثًا إلى جميع المشتركين المهتمين.

        Args:
            event_type (str): نوع الحدث.
            payload (Dict[str, Any]): حمولة (بيانات) الحدث.
        """
        raise NotImplementedError

    @abstractmethod
    async def send_command(self, command_type: str, payload: Dict[str, Any]) -> Any:
        """يرسل أمرًا إلى معالج واحد محدد ويتوقع استجابة.

        Args:
            command_type (str): نوع الأمر.
            payload (Dict[str, Any]): حمولة (بيانات) الأمر.

        Returns:
            Any: استجابة من معالج الأمر.
        """
        raise NotImplementedError

    @abstractmethod
    async def register_event_handler(self, event_type: str, handler: Callable[..., Any]) -> None:
        """يسجل معالجًا لحدث معين.

        Args:
            event_type (str): نوع الحدث الذي سيتعامل معه المعالج.
            handler (Callable[..., Any]): الدالة التي ستعالج الحدث.
        """
        raise NotImplementedError

    @abstractmethod
    async def register_command_handler(self, command_type: str, handler: Callable[..., Any]) -> None:
        """يسجل معالجًا لأمر معين.

        Args:
            command_type (str): نوع الأمر الذي سيتعامل معه المعالج.
            handler (Callable[..., Any]): الدالة التي ستعالج الأمر.
        """
        raise NotImplementedError


class MessagingBus(IMessagingBus):
    """تنفيذ Messaging Bus.

    مسؤول عن توجيه الأحداث والأوامر إلى المعالجات المناسبة.
    """

    def __init__(self) -> None:
        self._event_handlers: Dict[str, List[Callable[..., Any]]] = {}
        self._command_handlers: Dict[str, Callable[..., Any]] = {}
        logger.info("MessagingBus instance created.")

    async def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        logger.info("Publishing event %s with payload %s", event_type, payload)
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(payload)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error handling event %s with handler %s: %s", event_type, handler.__name__, e)

    async def send_command(self, command_type: str, payload: Dict[str, Any]) -> Any:
        logger.info("Sending command %s with payload %s", command_type, payload)
        handler = self._command_handlers.get(command_type)
        if not handler:
            logger.error("No handler registered for command %s", command_type)
            raise ValueError(f"No handler registered for command {command_type}")
        try:
            return await handler(payload)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error handling command %s with handler %s: %s", command_type, handler.__name__, e)
            raise

    async def register_event_handler(self, event_type: str, handler: Callable[..., Any]) -> None:
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.info("Registered event handler for %s: %s", event_type, handler.__name__)

    async def register_command_handler(self, command_type: str, handler: Callable[..., Any]) -> None:
        if command_type in self._command_handlers:
            logger.warning("Command handler already registered for %s. Overwriting.", command_type)
        self._command_handlers[command_type] = handler
        logger.info("Registered command handler for %s: %s", command_type, handler.__name__)
