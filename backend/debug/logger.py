"""
Centralized logging for the debug terminal.

Provides a custom logging handler that sends structured log events to the
LogStore, which can then be streamed to the frontend via SSE.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from backend.debug.store import LogEvent, get_log_store


# Valid log levels
VALID_LEVELS = {"DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}

# Valid sources
VALID_SOURCES = {"frontend", "backend", "api", "trading", "loader", "system"}

# Sensitive keys that should be redacted
SENSITIVE_KEYS = {
    "password",
    "secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "auth",
    "credentials",
    "private_key",
}


def redact_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """
    Redact sensitive values from a dictionary.

    Recursively walks the dictionary and replaces values for keys that match
    sensitive patterns with '[REDACTED]'.
    """
    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = redact_sensitive(value)
        else:
            result[key] = value
    return result


class DebugTerminalHandler(logging.Handler):
    """
    Custom logging handler that sends log records to the debug terminal.

    This handler converts Python logging.LogRecord objects into structured
    LogEvent objects and adds them to the global LogStore.
    """

    def __init__(
        self,
        source: str = "backend",
        level: int = logging.NOTSET,
    ):
        super().__init__(level)
        if source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {source}. Must be one of {VALID_SOURCES}")
        self.source = source

    def emit(self, record: logging.LogRecord) -> None:
        """Convert a LogRecord to a LogEvent and add it to the store."""
        try:
            # Determine the log level
            level = record.levelname
            if level not in VALID_LEVELS:
                level = "INFO"

            # Get the message
            message = self.format(record)

            # Get module name
            module = record.name

            # Get exception info if present
            exception = None
            if record.exc_info:
                exception = "".join(traceback.format_exception(*record.exc_info))

            # Get any extra fields from the record
            details = None
            if hasattr(record, "details") and isinstance(record.details, dict):
                details = redact_sensitive(record.details)

            # Get request_id if present
            request_id = getattr(record, "request_id", None)

            # Create the log event
            event = LogEvent(
                timestamp=datetime.now(timezone.utc).timestamp(),
                level=level,
                source=self.source,
                message=message,
                module=module,
                request_id=request_id,
                details=details,
                exception=exception,
            )

            # Add to the global store
            get_log_store().add(event)

        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)


def setup_debug_logging(
    log_level: int = logging.INFO,
    include_console: bool = True,
) -> None:
    """
    Set up logging to include the debug terminal handler.

    Args:
        log_level: Minimum log level to capture.
        include_console: Whether to also log to console (stderr).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add console handler if requested
    if include_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            "%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Add debug terminal handler for backend events
    terminal_handler = DebugTerminalHandler(source="backend", level=log_level)
    terminal_formatter = logging.Formatter("%(message)s")
    terminal_handler.setFormatter(terminal_formatter)
    root_logger.addHandler(terminal_handler)


def log_event(
    level: str,
    message: str,
    source: str = "backend",
    module: Optional[str] = None,
    request_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    exception: Optional[str] = None,
) -> None:
    """
    Log a structured event directly to the debug terminal.

    This is useful for logging events that don't fit neatly into Python's
    logging framework, such as frontend events received via API.

    Args:
        level: Log level (DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL).
        message: Human-readable log message.
        source: Event source (frontend, backend, api, trading, loader, system).
        module: Originating module or component.
        request_id: Correlation ID for the event.
        details: Optional structured metadata.
        exception: Optional exception information.
    """
    if level not in VALID_LEVELS:
        level = "INFO"
    if source not in VALID_SOURCES:
        source = "system"

    # Redact sensitive data
    if details:
        details = redact_sensitive(details)

    event = LogEvent(
        timestamp=datetime.now(timezone.utc).timestamp(),
        level=level,
        source=source,
        message=message,
        module=module,
        request_id=request_id,
        details=details,
        exception=exception,
    )

    get_log_store().add(event)
