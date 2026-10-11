# Debug Terminal - User Guide

## Overview

The Debug Terminal is a professional real-time log viewer and diagnostic tool integrated into the TradingAutomation dashboard. It provides comprehensive visibility into backend operations, API requests, trading system events, and application diagnostics.

## Accessing the Debug Terminal

1. Start the backend server:
   ```bash
   python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
   ```

2. Start the frontend:
   ```bash
   cd frontend
   npm run dev
   ```

3. Open your browser to `http://localhost:5173`

4. Click on the **Debug Terminal** tab in the navigation bar

## Features

### Real-Time Log Streaming
- Logs stream in real-time via Server-Sent Events (SSE)
- Automatic reconnection on connection loss
- Connection status indicator (green = connected, yellow = reconnecting, red = disconnected)

### Log Filtering
- **Level Filter**: DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
- **Source Filter**: Frontend, Backend, API, Trading Engine, Data Loader, System
- **Time Filter**: Last minute, Last 5 minutes, Last hour, All time
- **Search**: Full-text search across messages, modules, and request IDs

### Log Management
- **Pause/Resume**: Pause the log stream without losing incoming events
- **Auto-scroll**: Toggle automatic scrolling to latest events
- **Clear**: Clear the visible log buffer (does not delete persistent logs)
- **Export**: Download filtered logs as JSON
- **Copy**: Click the copy icon on any log entry to copy it to clipboard

### Event Details
Click on any log entry to expand and view:
- Full timestamp (ISO 8601)
- Module name
- Request ID (for API requests)
- Structured metadata (if available)
- Exception stack traces (for errors)

### Summary Statistics
The stats bar shows real-time counts:
- Total events in buffer
- Events by level (Debug, Info, Success, Warning, Error, Critical)
- Buffer utilization percentage

## Architecture

### Backend Components

#### Log Store (`backend/debug/store.py`)
- Thread-safe, bounded in-memory buffer (default: 10,000 events)
- Automatic eviction of oldest events when buffer is full
- Subscriber notification system for SSE streaming

#### Logger (`backend/debug/logger.py`)
- Custom Python logging handler that captures all log events
- Structured log format with timestamp, level, source, message, metadata
- Automatic redaction of sensitive data (passwords, API keys, tokens)
- Integration with Python's standard logging framework

#### API Routes (`backend/debug/routes.py`)
- `GET /api/debug/logs` - Retrieve recent logs with filtering
- `GET /api/debug/logs/stream` - SSE endpoint for live streaming
- `GET /api/debug/stats` - Get buffer statistics
- `POST /api/debug/logs` - Accept frontend log events
- `DELETE /api/debug/logs` - Clear the log buffer
- `GET /api/debug/health` - Health check endpoint

### Frontend Components

#### DebugTerminalPage (`frontend/src/components/DebugTerminalPage.tsx`)
- Real-time log viewer with SSE connection
- Filtering and search functionality
- Pause/resume and auto-scroll controls
- Export and copy functionality
- Expandable event details

## Log Levels

- **DEBUG**: Detailed diagnostic information (development)
- **INFO**: General informational messages
- **SUCCESS**: Successful operations (custom level)
- **WARNING**: Potential issues that don't prevent operation
- **ERROR**: Errors that prevent specific operations
- **CRITICAL**: Severe errors that may crash the application

## Log Sources

- **frontend**: Events from the React application
- **backend**: Events from the FastAPI backend
- **api**: API request/response events
- **trading**: Trading engine events
- **loader**: Data loading and refresh events
- **system**: System-level events (startup, shutdown, config)

## Security

### Sensitive Data Redaction
The logger automatically redacts sensitive information:
- Passwords
- API keys
- Access tokens
- Private keys
- Credentials

These values are replaced with `[REDACTED]` before being logged.

### Access Control
The debug terminal endpoints are currently open for local development. For production deployment:
- Add authentication middleware
- Restrict access to authorized users only
- Consider rate limiting to prevent log flooding

## Configuration

### Buffer Size
To change the maximum buffer size, edit `backend/debug/store.py`:

```python
def __init__(self, max_size: int = 10000):  # Change this value
    ...
```

### Log Level
To change the minimum log level, edit `backend/main.py`:

```python
setup_debug_logging(log_level=logging.INFO, include_console=True)
# Change to logging.DEBUG for more verbose logging
```

## Performance Considerations

- The log buffer is bounded to prevent memory issues
- SSE connections are automatically cleaned up when the component unmounts
- Log events are written asynchronously to avoid blocking
- Large stack traces are truncated to prevent excessive data transfer

## Troubleshooting

### Connection Issues
If the terminal shows "Disconnected":
1. Check that the backend server is running
2. Verify the backend is accessible at `http://127.0.0.1:8000`
3. Check browser console for CORS or network errors
4. The terminal will automatically attempt to reconnect every 3 seconds

### No Logs Appearing
If the terminal is connected but no logs appear:
1. Perform an action in the application (navigate, refresh data, etc.)
2. Check that the backend is generating logs (check console output)
3. Verify filter settings aren't excluding all logs

### High Memory Usage
If memory usage is high:
1. Reduce the buffer size in `backend/debug/store.py`
2. Clear the log buffer using the "Clear" button
3. Export logs to file and clear the buffer

## API Examples

### Retrieve Recent Logs
```bash
curl http://127.0.0.1:8000/api/debug/logs?limit=100&level=ERROR
```

### Stream Logs via SSE
```bash
curl -N http://127.0.0.1:8000/api/debug/logs/stream
```

### Get Statistics
```bash
curl http://127.0.0.1:8000/api/debug/stats
```

### Clear Log Buffer
```bash
curl -X DELETE http://127.0.0.1:8000/api/debug/logs
```

### Send Frontend Log
```bash
curl -X POST http://127.0.0.1:8000/api/debug/logs \
  -H "Content-Type: application/json" \
  -d '{
    "level": "ERROR",
    "message": "Test error from frontend",
    "source": "frontend",
    "module": "DebugTerminal",
    "details": {"component": "App"}
  }'
```

## Future Enhancements

Potential improvements for future versions:
- Persistent log storage (file-based or database)
- Log rotation and archival
- Advanced search with regular expressions
- Log aggregation across multiple instances
- Integration with external monitoring systems (Prometheus, Grafana)
- Custom log levels and categories
- Log export in multiple formats (CSV, plain text)
- Real-time log analysis and alerting

## Support

For issues or questions:
1. Check the browser console for frontend errors
2. Check the backend console for Python errors
3. Review the debug terminal logs for diagnostic information
4. Verify all dependencies are installed correctly

---

**Version**: 1.0.0  
**Last Updated**: 2026-10-11
