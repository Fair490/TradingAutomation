# fix_backend.ps1
# Automated fix for backend startup failure
# Run this from D:\Automation\TradingAutomation

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fixing Backend Startup Failure" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "backend")) {
    Write-Host "ERROR: backend directory not found!" -ForegroundColor Red
    Write-Host "Please run this script from D:\Automation\TradingAutomation" -ForegroundColor Yellow
    exit 1
}

# Step 1: Create backend/main.py if missing
Write-Host "Step 1: Checking backend\main.py..." -ForegroundColor Yellow
if (-not (Test-Path "backend\main.py")) {
    Write-Host "  Creating backend\main.py..." -ForegroundColor Yellow
    $mainContent = @'
"""
Market Health Dashboard - FastAPI backend.

Run from the repository root:

    Windows:  .\.venv\Scripts\python.exe -m uvicorn backend.main:app \
                  --host 127.0.0.1 --port 8000 --reload --reload-dir backend
    macOS/Linux:
              ./.venv/bin/python -m uvicorn backend.main:app \
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
    with store.session() as con:
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
'@
    $mainContent | Out-File -FilePath "backend\main.py" -Encoding UTF8
    Write-Host "  Created backend\main.py" -ForegroundColor Green
} else {
    Write-Host "  backend\main.py already exists" -ForegroundColor Green
}

# Step 2: Create missing __init__.py files
Write-Host ""
Write-Host "Step 2: Checking __init__.py files..." -ForegroundColor Yellow

$initFiles = @(
    "backend\__init__.py",
    "backend\api\__init__.py",
    "backend\compute\__init__.py",
    "backend\loaders\__init__.py",
    "backend\scripts\__init__.py"
)

foreach ($file in $initFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "  Creating $file..." -ForegroundColor Yellow
        New-Item -Path $file -ItemType File -Force | Out-Null
        Write-Host "  Created $file" -ForegroundColor Green
    } else {
        Write-Host "  $file exists" -ForegroundColor Green
    }
}

# Step 3: Verify critical files
Write-Host ""
Write-Host "Step 3: Verifying critical files..." -ForegroundColor Yellow

$criticalFiles = @(
    "backend\main.py",
    "backend\config.py",
    "backend\api\routes.py",
    "backend\api\schemas.py",
    "backend\api\refresh_job.py",
    "backend\api\responses.py",
    "backend\compute\breadth.py",
    "backend\compute\series.py",
    "backend\loaders\store.py",
    "backend\loaders\prices.py",
    "backend\loaders\universe.py"
)

$missingCritical = @()
foreach ($file in $criticalFiles) {
    if (Test-Path $file) {
        Write-Host "  OK: $file" -ForegroundColor Green
    } else {
        Write-Host "  MISSING: $file" -ForegroundColor Red
        $missingCritical += $file
    }
}

if ($missingCritical.Count -gt 0) {
    Write-Host ""
    Write-Host "ERROR: Missing critical files:" -ForegroundColor Red
    $missingCritical | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "These files are required for the backend to function." -ForegroundColor Yellow
    Write-Host "Please ensure you have the complete backend code." -ForegroundColor Yellow
    exit 1
}

# Step 4: Test import
Write-Host ""
Write-Host "Step 4: Testing import..." -ForegroundColor Yellow

$testResult = & .\.venv\Scripts\python.exe -c "import backend.main; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Import successful" -ForegroundColor Green
} else {
    Write-Host "  Import failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error output:" -ForegroundColor Red
    Write-Host $testResult -ForegroundColor Red
    Write-Host ""
    Write-Host "Common causes:" -ForegroundColor Yellow
    Write-Host "  1. Missing dependencies - Run: .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt" -ForegroundColor Yellow
    Write-Host "  2. Python path issue - Make sure you are in D:\Automation\TradingAutomation" -ForegroundColor Yellow
    exit 1
}

# Step 5: Check dependencies
Write-Host ""
Write-Host "Step 5: Checking dependencies..." -ForegroundColor Yellow

$depCheck = & .\.venv\Scripts\python.exe -c "import fastapi, uvicorn, duckdb, pandas; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  All dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  Missing dependencies detected" -ForegroundColor Red
    Write-Host "  Installing dependencies..." -ForegroundColor Yellow
    & .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
}

# Final summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fix Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now start the backend server with:" -ForegroundColor White
Write-Host ""
Write-Host "  .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend" -ForegroundColor Cyan
Write-Host ""
Write-Host "The server will be available at: http://127.0.0.1:8000" -ForegroundColor White
Write-Host "API documentation at: http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Your existing data (backend\data\market.duckdb) is safe and unchanged." -ForegroundColor Green
Write-Host ""
