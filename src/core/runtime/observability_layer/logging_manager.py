from abc import ABC, abstractmethod
from typing import Any, Dict
import logging
import sys

class ILoggingManager(ABC):
    @abstractmethod
    def get_logger(self, name: str) -> logging.Logger:
        """
        يحصل على مسجل (logger) بالاسم المحدد.

        Args:
            name (str): اسم المسجل.

        Returns:
            logging.Logger: كائن المسجل.
        """
        raise NotImplementedError

    @abstractmethod
    def configure_logging(self, level: str = "INFO", handlers: list = None):
        """
        يقوم بتكوين إعدادات التسجيل (logging).

        Args:
            level (str): مستوى التسجيل الافتراضي (مثل "INFO", "DEBUG").
            handlers (list): قائمة بمعالجات التسجيل (logging handlers).
        """
        raise NotImplementedError

class LoggingManager(ILoggingManager):
    def __init__(self):
        self._loggers: Dict[str, logging.Logger] = {}
        self.configure_logging() # Configure default logging on initialization

    def get_logger(self, name: str) -> logging.Logger:
        if name not in self._loggers:
            logger = logging.getLogger(name)
            logger.propagate = True # Allow messages to propagate to the root logger
            self._loggers[name] = logger
        return self._loggers[name]

    def configure_logging(self, level: str = "INFO", handlers: list = None):
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Clear all existing handlers from the root logger
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()

        effective_handlers = handlers
        if effective_handlers is None:
            # Default handler: Console output (writes to sys.stderr by default)
            console_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            effective_handlers = [console_handler]

        # Add effective handlers to the root logger
        for handler in effective_handlers:
            root_logger.addHandler(handler)
