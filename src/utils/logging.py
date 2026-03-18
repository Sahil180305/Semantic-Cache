"""
Structured logging utilities for Semantic Cache system.

Provides JSON-formatted logging with context tracking for observability.
"""

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any, Dict, Optional
from datetime import datetime

# Context variables for tracking request/operation context
request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
tenant_id: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
operation_name: ContextVar[Optional[str]] = ContextVar("operation_name", default=None)


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

        # Add context variables if set
        if rid := request_id.get():
            log_data["request_id"] = rid
        if tid := tenant_id.get():
            log_data["tenant_id"] = tid
        if uid := user_id.get():
            log_data["user_id"] = uid
        if op := operation_name.get():
            log_data["operation"] = op

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        # Add extra fields if present
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_data.update(record.extra)

        return json.dumps(log_data)


class StructuredLogger:
    """Wrapper around Python logger for structured logging with context."""

    def __init__(self, name: str):
        """Initialize structured logger.

        Args:
            name: Logger name (typically __name__)
        """
        self._logger = logging.getLogger(name)

    def info(
        self, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs
    ) -> None:
        """Log info message with optional structured data."""
        self._log("info", message, extra, **kwargs)

    def debug(
        self, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs
    ) -> None:
        """Log debug message with optional structured data."""
        self._log("debug", message, extra, **kwargs)

    def warning(
        self, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs
    ) -> None:
        """Log warning message with optional structured data."""
        self._log("warning", message, extra, **kwargs)

    def error(
        self, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs
    ) -> None:
        """Log error message with optional structured data."""
        self._log("error", message, extra, **kwargs)

    def critical(
        self, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs
    ) -> None:
        """Log critical message with optional structured data."""
        self._log("critical", message, extra, **kwargs)

    def exception(
        self, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs
    ) -> None:
        """Log exception with traceback and optional structured data."""
        self._log("error", message, extra, exc_info=True, **kwargs)

    def _log(
        self,
        level: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """Internal logging method."""
        log_record = self._logger.makeRecord(
            self._logger.name,
            getattr(logging, level.upper()),
            "", 0, message, (), None
        )
        if extra:
            log_record.extra = extra
        getattr(self._logger, level)(message)

    def set_context(
        self,
        request_id_val: Optional[str] = None,
        tenant_id_val: Optional[str] = None,
        user_id_val: Optional[str] = None,
        operation_name_val: Optional[str] = None,
    ) -> None:
        """Set logging context variables.

        Args:
            request_id_val: Request ID for tracing
            tenant_id_val: Tenant ID
            user_id_val: User ID
            operation_name_val: Current operation name
        """
        if request_id_val:
            request_id.set(request_id_val)
        if tenant_id_val:
            tenant_id.set(tenant_id_val)
        if user_id_val:
            user_id.set(user_id_val)
        if operation_name_val:
            operation_name.set(operation_name_val)

    def clear_context(self) -> None:
        """Clear all logging context."""
        request_id.set(None)
        tenant_id.set(None)
        user_id.set(None)
        operation_name.set(None)


def configure_logging(
    level: str = "INFO", format_type: str = "json", log_file: Optional[str] = None
) -> None:
    """Configure root logger with JSON formatting.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Format type ('json' or 'text')
        log_file: Optional file path for file logging
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    if format_type == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)
