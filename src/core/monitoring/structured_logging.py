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
import tempfile
from datetime import datetime
from typing import Dict, Optional

from src.api.middleware.request_id import request_id_var
from src.core.monitoring.secret_masking import mask_dict_values

# /tmp does not survive a container restart -- LOG_DIR lets deployment
# mount a durable volume (see docker-compose.yml's `app_logs` volume);
# defaults to /var/log/basirah, which is still overridden by an explicit
# `log_dir=` argument. In CI/test environments (GitHub Actions' ubuntu-latest
# runs as a non-root `runner` user with no write access to /var/log), set
# LOG_DIR to a writable path such as ${RUNNER_TEMP}/basirah-logs -- see
# .github/workflows/ci.yml. _ensure_writable_log_dir below is a second,
# independent line of defense for whenever that isn't done (or a real
# production /var/log/basirah mount is misconfigured): it never lets a
# directory-creation failure crash the app or silently disable logging.
_DEFAULT_LOG_DIR = os.getenv("LOG_DIR", "/var/log/basirah")


def _ensure_writable_log_dir(configured_dir: str) -> str:
    """Creates `configured_dir` (like the old unconditional
    `os.makedirs(log_dir, exist_ok=True)` this replaces) but never lets a
    permission failure propagate as an unhandled exception -- that would
    crash application boot over what is, at worst, a missing log volume.

    On PermissionError (or any other OSError -- a read-only filesystem
    can also raise e.g. EROFS, which is not a PermissionError subclass
    but is exactly the same class of "can't write here" problem this
    exists to handle), falls back to a process-local, always-writable
    temp directory and returns *that* path instead, so every caller
    (StructuredLogger.__init__) transparently logs to wherever logging
    actually ended up working.

    The fallback is deliberately reported to stderr directly (`print`),
    not through this module's own logger -- no logger/handler exists
    yet at this point in initialization, and routing this warning
    through the very logging system being constructed would be
    recursive. Nothing here ever prints a secret: only directory paths
    and the OS error's own (already sanitized) message are involved.

    If even the fallback directory can't be created, this re-raises --
    logging must never be silently disabled; a genuinely unwritable
    filesystem (fallback included) is a real deployment problem that
    should fail loudly, not vanish into a no-op logger.
    """
    try:
        os.makedirs(configured_dir, exist_ok=True)
        return configured_dir
    except (PermissionError, OSError) as exc:
        fallback_dir = os.path.join(
            os.getenv("RUNNER_TEMP") or tempfile.gettempdir(), "basirah-logs"
        )
        print(
            f"WARNING: could not create configured log directory {configured_dir!r} "
            f"({type(exc).__name__}: {exc}) -- falling back to {fallback_dir!r} for "
            f"this process's logs. Set LOG_DIR to a writable path to use a specific "
            f"directory instead.",
            file=sys.stderr,
        )
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir


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

        request_id = request_id_var.get()
        if request_id is not None:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present -- masked by key name (e.g. a
        # future call site accidentally passing api_key=... or
        # database_url=... into log.info(**extra_fields) must not
        # leak the real value into a log line or Sentry breadcrumb).
        if hasattr(record, "extra_fields"):
            log_data.update(mask_dict_values(record.extra_fields))

        return json.dumps(log_data)


class StructuredLogger:
    """Structured logging wrapper for Basirah."""

    def __init__(
        self,
        name: str,
        log_dir: Optional[str] = None,
        log_level: str = "INFO",
        max_bytes: int = 10485760,  # 10MB
        backup_count: int = 10,
    ):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            log_dir: Directory for log files (defaults to LOG_DIR env var,
                falling back to /var/log/basirah)
            log_level: Logging level
            max_bytes: Maximum file size before rotation
            backup_count: Number of backup files to keep
        """
        log_dir = log_dir or _DEFAULT_LOG_DIR
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level))

        # Create log directory if it doesn't exist -- falls back to a
        # writable temp directory (never raises, never silently
        # disables logging) if `log_dir` isn't writable. See
        # _ensure_writable_log_dir's docstring above.
        log_dir = _ensure_writable_log_dir(log_dir)

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


def init_logging(log_dir: Optional[str] = None, log_level: str = "INFO") -> None:
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
