"""
API routes for the debug terminal.

Provides endpoints for retrieving, streaming, and managing debug logs.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.debug.logger import VALID_LEVELS, VALID_SOURCES, log_event
from backend.debug.store import get_log_store


router = APIRouter(prefix="/api/debug", tags=["debug"])


# --------------------------------------------------------------------------- #
# Request/Response Models
# --------------------------------------------------------------------------- #


class FrontendLogEntry(BaseModel):
    """Log entry received from the frontend."""

    level: str = Field(..., description="Log level")
    message: str = Field(..., description="Log message")
    source: str = Field(default="frontend", description="Event source")
    module: Optional[str] = Field(None, description="Originating module")
    request_id: Optional[str] = Field(None, description="Correlation ID")
    details: Optional[dict] = Field(None, description="Structured metadata")
    exception: Optional[str] = Field(None, description="Exception information")


class LogStats(BaseModel):
    """Summary statistics about the log buffer."""

    total: int
    max_size: int
    level_debug: int = 0
    level_info: int = 0
    level_success: int = 0
    level_warning: int = 0
    level_error: int = 0
    level_critical: int = 0


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/logs")
def get_logs(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    source: Optional[str] = Query(None, description="Filter by source"),
    since: Optional[float] = Query(None, description="Only events after this timestamp"),
) -> list[dict]:
    """
    Retrieve recent log events with optional filtering.

    Returns a list of log events, most recent first.
    """
    # Validate level filter
    if level and level not in VALID_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level: {level}. Must be one of {', '.join(VALID_LEVELS)}",
        )

    # Validate source filter
    if source and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source: {source}. Must be one of {', '.join(VALID_SOURCES)}",
        )

    store = get_log_store()
    events = store.get_recent(limit=limit, level=level, source=source, since=since)

    return [event.to_dict() for event in events]


@router.get("/logs/stream")
async def stream_logs(
    level: Optional[str] = Query(None, description="Filter by log level"),
    source: Optional[str] = Query(None, description="Filter by source"),
):
    """
    Stream log events via Server-Sent Events (SSE).

    This endpoint maintains a long-lived connection and pushes new log events
    to the client as they occur. The client should handle reconnection.
    """
    # Validate filters
    if level and level not in VALID_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level: {level}. Must be one of {', '.join(VALID_LEVELS)}",
        )

    if source and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source: {source}. Must be one of {', '.join(VALID_SOURCES)}",
        )

    store = get_log_store()

    async def event_generator():
        """Generate SSE events from the log store."""
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': time.time()})}\n\n"

        # Subscribe to new events
        subscriber = store.subscribe()

        try:
            # Send recent events first (last 100)
            recent = store.get_recent(limit=100, level=level, source=source)
            for event in reversed(recent):  # Send oldest first
                event_dict = event.to_dict()
                event_dict["type"] = "log"
                yield f"data: {json.dumps(event_dict)}\n\n"

            # Then stream new events as they arrive
            while True:
                # Wait for a new event (with timeout to check for client disconnect)
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, subscriber.wait, 1.0),
                        timeout=30.0,
                    )
                    subscriber.clear()

                    # Get the latest event
                    latest = store.get_recent(limit=1, level=level, source=source)
                    if latest:
                        event_dict = latest[0].to_dict()
                        event_dict["type"] = "log"
                        yield f"data: {json.dumps(event_dict)}\n\n"

                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            pass
        finally:
            store.unsubscribe(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/stats", response_model=LogStats)
def get_stats() -> dict:
    """
    Get summary statistics about the log buffer.

    Returns counts of events by level and total buffer size.
    """
    store = get_log_store()
    return store.get_stats()


@router.post("/logs")
def post_frontend_log(entry: FrontendLogEntry) -> dict:
    """
    Accept a log entry from the frontend.

    This allows the frontend to send error reports and diagnostic information
    to the debug terminal.
    """
    log_event(
        level=entry.level,
        message=entry.message,
        source=entry.source,
        module=entry.module,
        request_id=entry.request_id,
        details=entry.details,
        exception=entry.exception,
    )

    return {"status": "ok"}


@router.delete("/logs")
def clear_logs() -> dict:
    """
    Clear all events from the log buffer.

    This only clears the in-memory buffer, not persistent log files.
    """
    store = get_log_store()
    store.clear()
    return {"status": "ok", "message": "Log buffer cleared"}


@router.get("/health")
def debug_health() -> dict:
    """
    Debug terminal health check.

    Returns information about the log buffer and connection status.
    """
    store = get_log_store()
    stats = store.get_stats()

    return {
        "status": "ok",
        "terminal": "debug",
        "buffer_total": stats["total"],
        "buffer_max": stats["max_size"],
        "buffer_utilization": round(stats["total"] / stats["max_size"] * 100, 2),
    }
