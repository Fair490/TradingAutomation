"""
Market Health Dashboard - FastAPI backend.

Run from the repository root:

    Windows:  .\\.venv\\Scripts\\python.exe -m uvicorn backend.main:app \\
                  --host 127.0.0.1 --port 8000 --reload --reload-dir backend
    macOS/Linux:
              ./.venv/bin/python -m uvicorn backend.main:app \\
                  --host 127.0.0.1 --port 8000 --reload --reload-dir backend

The React frontend (``cd frontend && npm run dev``) proxies /api to this
server, so there is nothing else to configure.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.api.responses import SafeJSONResponse
from backend.api.routes import router
from backend.debug.logger import setup_debug_logging
from backend.debug.routes import router as debug_router
from backend.loaders import store

# Set up debug logging (includes console and debug terminal)
setup_debug_logging(log_level=logging.INFO, include_console=True)
log = logging.getLogger("market-health")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.ensure_dirs()
    with store.session() as con:  # creates the schema on first boot
        n = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    log.info("DuckDB ready at %s (%s price rows)", config.DB_PATH, f"{n:,}")
    if n == 0:
        log.info("No data yet - POST /api/refresh (or use the Refresh button).")
    
    # Log startup event to debug terminal
    from backend.debug.logger import log_event
    log_event(
        level="INFO",
        message="Backend server started successfully",
        source="backend",
        module="main",
        details={"database_rows": n, "database_path": str(config.DB_PATH)},
    )
    
    yield
    
    # Log shutdown event
    log_event(
        level="INFO",
        message="Backend server shutting down",
        source="backend",
        module="main",
    )
    store.reset_connection()


app = FastAPI(
    title="Market Health Dashboard API",
    description=(
        "Breadth, advance/decline, global indices, macro and commodities for "
        "the Nifty Total Market universe. Data source: Yahoo Finance via "
        "yfinance; storage: DuckDB."
    ),
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,
)

# The Vite dev server proxies /api, so CORS is only needed if the frontend is
# ever served from a different origin. Keep it permissive for local use.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(debug_router)


# Middleware to log API requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log API requests with timing and request ID."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Add request_id to request state
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Log the request
        log.info(
            f"{request.method} {request.url.path} - {response.status_code} ({duration:.3f}s)",
            extra={
                "request_id": request_id,
                "details": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            },
        )

        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start_time
        log.error(
            f"{request.method} {request.url.path} - ERROR: {str(e)} ({duration:.3f}s)",
            extra={
                "request_id": request_id,
                "details": {
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 2),
                },
            },
            exc_info=True,
        )
        raise


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "market-health-dashboard"}


@app.get("/")
def root() -> dict:
    return {
        "service": "Market Health Dashboard API",
        "docs": "/docs",
        "frontend": "run `npm run dev` in ./frontend",
    }
