"""
Structured logging for Basirah production environment.

Provides JSON-formatted logs with:
- Rotating file handlers
- Multiple log levels
- Audit logging
- Exception tracking
- Startup/shutdown logging
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Dict


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class StructuredLogger:
    """Structured logging wrapper for Basirah."""

    def __init__(
        self,
        name: str,
        log_dir: str = "/tmp/basirah_logs",
        log_level: str = "INFO",
        max_bytes: int = 10485760,  # 10MB
        backup_count: int = 10,
    ):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            log_dir: Directory for log files
            log_level: Logging level
            max_bytes: Maximum file size before rotation
            backup_count: Number of backup files to keep
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level))

        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)

        # JSON formatter
        json_formatter = JSONFormatter()

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(json_formatter)
        self.logger.addHandler(console_handler)

        # File handler with rotation
        log_file = os.path.join(log_dir, f"{name}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(json_formatter)
        self.logger.addHandler(file_handler)

        # Audit log handler (separate file for audit events)
        audit_log_file = os.path.join(log_dir, f"{name}_audit.log")
        audit_handler = logging.handlers.RotatingFileHandler(
            audit_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        audit_handler.setFormatter(json_formatter)
        self.audit_logger = logging.getLogger(f"{name}.audit")
        self.audit_logger.addHandler(audit_handler)

    def info(self, message: str, **extra_fields) -> None:
        """Log info message with extra fields."""
        record = self.logger.makeRecord(
            self.logger.name,
            logging.INFO,
            "(unknown file)",
            0,
            message,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def error(self, message: str, **extra_fields) -> None:
        """Log error message with extra fields."""
        record = self.logger.makeRecord(
            self.logger.name,
            logging.ERROR,
            "(unknown file)",
            0,
            message,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def warning(self, message: str, **extra_fields) -> None:
        """Log warning message with extra fields."""
        record = self.logger.makeRecord(
            self.logger.name,
            logging.WARNING,
            "(unknown file)",
            0,
            message,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def debug(self, message: str, **extra_fields) -> None:
        """Log debug message with extra fields."""
        record = self.logger.makeRecord(
            self.logger.name,
            logging.DEBUG,
            "(unknown file)",
            0,
            message,
            (),
            None,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def exception(self, message: str, exc_info=None, **extra_fields) -> None:
        """Log exception with extra fields."""
        record = self.logger.makeRecord(
            self.logger.name,
            logging.ERROR,
            "(unknown file)",
            0,
            message,
            (),
            exc_info,
        )
        record.extra_fields = extra_fields
        self.logger.handle(record)

    def audit(self, event: str, **details) -> None:
        """Log audit event."""
        audit_data = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            **details,
        }
        self.audit_logger.info(json.dumps(audit_data))

    def startup(self, component: str, version: str = None, **details) -> None:
        """Log startup event."""
        self.info(
            f"Component started: {component}",
            component=component,
            version=version,
            event_type="startup",
            **details,
        )

    def shutdown(self, component: str, reason: str = None, **details) -> None:
        """Log shutdown event."""
        self.info(
            f"Component shutdown: {component}",
            component=component,
            reason=reason,
            event_type="shutdown",
            **details,
        )


# Global logger instances
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(name: str) -> StructuredLogger:
    """Get or create logger instance."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


def init_logging(log_dir: str = "/tmp/basirah_logs", log_level: str = "INFO") -> None:
    """Initialize logging system."""
    # Create main logger
    main_logger = StructuredLogger(
        "basirah",
        log_dir=log_dir,
        log_level=log_level,
    )
    _loggers["basirah"] = main_logger

    # Create component loggers
    components = [
        "runtime",
        "agent",
        "market_data",
        "database",
        "api",
    ]

    for component in components:
        _loggers[component] = StructuredLogger(
            f"basirah.{component}",
            log_dir=log_dir,
            log_level=log_level,
        )

    main_logger.startup("basirah", version="1.0.0")
