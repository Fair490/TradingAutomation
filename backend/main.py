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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.api.responses import SafeJSONResponse
from backend.api.routes import router
from backend.loaders import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("market-health")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.ensure_dirs()
    with store.session() as con:  # creates the schema on first boot
        n = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    log.info("DuckDB ready at %s (%s price rows)", config.DB_PATH, f"{n:,}")
    if n == 0:
        log.info("No data yet - POST /api/refresh (or use the Refresh button).")
    yield
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
