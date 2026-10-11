"""
In-memory log buffer for the debug terminal.

Provides a bounded, thread-safe store of structured log events that the
frontend can retrieve via SSE or REST endpoints.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Optional


class LogEvent:
    """A single structured log event."""

    __slots__ = (
        "timestamp",
        "level",
        "source",
        "message",
        "module",
        "request_id",
        "details",
        "exception",
    )

    def __init__(
        self,
        timestamp: float,
        level: str,
        source: str,
        message: str,
        module: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        exception: Optional[str] = None,
    ):
        self.timestamp = timestamp
        self.level = level
        self.source = source
        self.message = message
        self.module = module
        self.request_id = request_id
        self.details = details
        self.exception = exception

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }
        if self.module:
            result["module"] = self.module
        if self.request_id:
            result["request_id"] = self.request_id
        if self.details:
            result["details"] = self.details
        if self.exception:
            result["exception"] = self.exception
        return result


class LogStore:
    """
    Bounded, thread-safe in-memory log buffer.

    Events are stored in a deque with a maximum size. When the buffer is full,
    the oldest events are automatically discarded.
    """

    def __init__(self, max_size: int = 10000):
        self._buffer: Deque[LogEvent] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._subscribers: list[threading.Event] = []
        self._max_size = max_size

    def add(self, event: LogEvent) -> None:
        """Add a log event to the buffer."""
        with self._lock:
            self._buffer.append(event)
            # Notify all subscribers that a new event is available
            for subscriber in self._subscribers:
                subscriber.set()

    def get_recent(
        self,
        limit: int = 100,
        level: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[float] = None,
    ) -> list[LogEvent]:
        """
        Retrieve recent log events with optional filtering.

        Args:
            limit: Maximum number of events to return.
            level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            source: Filter by source (frontend, backend, api, trading, system).
            since: Only return events with timestamp >= since (Unix timestamp).

        Returns:
            List of LogEvent objects, most recent first.
        """
        with self._lock:
            events = list(self._buffer)

        # Apply filters
        if level:
            events = [e for e in events if e.level == level]
        if source:
            events = [e for e in events if e.source == source]
        if since:
            events = [e for e in events if e.timestamp >= since]

        # Sort by timestamp descending (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply limit
        return events[:limit]

    def clear(self) -> None:
        """Clear all events from the buffer."""
        with self._lock:
            self._buffer.clear()

    def subscribe(self) -> threading.Event:
        """
        Subscribe to new log events.

        Returns a threading.Event that will be set whenever a new event is added.
        The caller should call unsubscribe() when done.
        """
        event = threading.Event()
        with self._lock:
            self._subscribers.append(event)
        return event

    def unsubscribe(self, event: threading.Event) -> None:
        """Unsubscribe from new log events."""
        with self._lock:
            if event in self._subscribers:
                self._subscribers.remove(event)

    def get_stats(self) -> dict[str, int]:
        """Get summary statistics about the log buffer."""
        with self._lock:
            total = len(self._buffer)
            by_level: dict[str, int] = {}
            for event in self._buffer:
                by_level[event.level] = by_level.get(event.level, 0) + 1

            return {
                "total": total,
                "max_size": self._max_size,
                **{f"level_{k.lower()}": v for k, v in by_level.items()},
            }


# Global singleton instance
_log_store: Optional[LogStore] = None
_store_lock = threading.Lock()


def get_log_store() -> LogStore:
    """Get the global log store instance (creates it if needed)."""
    global _log_store
    if _log_store is None:
        with _store_lock:
            if _log_store is None:
                _log_store = LogStore(max_size=10000)
    return _log_store
