# Fix Backend Startup Failure - Complete Solution

## Root Cause

The error "Could not import module 'backend.main'" occurs because:
1. `backend/main.py` is missing in your local repository
2. Possibly `backend/__init__.py` or other `__init__.py` files are also missing
3. Your local repository has root-level `compute/`, `data/`, `loaders/` directories from an older structure, but the code now expects everything under `backend/`

## Solution Overview

The fix requires creating the missing files. All files are provided in this solution.

## Step-by-Step Fix

### Step 1: Create the missing backend/main.py file

Create `backend/main.py` with this exact content:

```python
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
```

### Step 2: Ensure all __init__.py files exist

Create these empty files if they don't exist:

- `backend/__init__.py`
- `backend/api/__init__.py`
- `backend/compute/__init__.py`
- `backend/loaders/__init__.py`
- `backend/scripts/__init__.py`

Each file should be empty (0 bytes).

### Step 3: Verify the structure

Run this PowerShell command to verify:

```powershell
$files = @(
    "backend\__init__.py",
    "backend\main.py",
    "backend\api\__init__.py",
    "backend\api\routes.py",
    "backend\api\schemas.py",
    "backend\api\refresh_job.py",
    "backend\api\responses.py",
    "backend\compute\__init__.py",
    "backend\loaders\__init__.py",
    "backend\config.py"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "✓ $file" -ForegroundColor Green
    } else {
        Write-Host "✗ $file MISSING" -ForegroundColor Red
    }
}
```

### Step 4: Test the import

```powershell
.\.venv\Scripts\python.exe -c "import backend.main; print('SUCCESS')"
```

If this succeeds, proceed to Step 5. If it fails with a different error, see the Troubleshooting section below.

### Step 5: Start the server

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Started server process
INFO:     DuckDB ready at ... (X price rows)
```

## Troubleshooting

### Error: "No module named 'backend'"

This means `backend/__init__.py` is missing. Create it:

```powershell
New-Item -Path backend\__init__.py -ItemType File -Force
```

### Error: "No module named 'fastapi'"

Install the dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Or install individually:

```powershell
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn duckdb pandas numpy yfinance pydantic
```

### Error: "No module named 'backend.api'"

This means `backend/api/__init__.py` is missing. Create it:

```powershell
New-Item -Path backend\api\__init__.py -ItemType File -Force
```

### Error: "No module named 'backend.compute'"

This means `backend/compute/__init__.py` is missing. Create it:

```powershell
New-Item -Path backend\compute\__init__.py -ItemType File -Force
```

### Error: "No module named 'backend.loaders'"

This means `backend/loaders/__init__.py` is missing. Create it:

```powershell
New-Item -Path backend\loaders\__init__.py -ItemType File -Force
```

## Important Notes

1. **Do NOT delete your existing data**: Your `backend/data/market.duckdb` file is safe and will not be affected.

2. **Root-level directories**: You have root-level `compute/`, `data/`, `loaders/` directories from an older structure. These are NOT used by the current code. The current code uses:
   - `backend/compute/`
   - `backend/data/`
   - `backend/loaders/`

3. **Database path**: The database is at `backend/data/market.duckdb` as defined in `backend/config.py`.

4. **Python path**: When running from the project root (`D:\Automation\TradingAutomation`), Python should automatically find the `backend` package because the current directory is in the Python path.

## Quick Fix Script

Save this as `fix_backend.ps1` and run it:

```powershell
# fix_backend.ps1
# Quick fix for backend startup failure

Write-Host "Fixing backend startup failure..." -ForegroundColor Cyan

# Create backend/main.py if missing
if (-not (Test-Path "backend\main.py")) {
    Write-Host "Creating backend\main.py..." -ForegroundColor Yellow
    @"
"""
Market Health Dashboard - FastAPI backend.
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
        "frontend": "run ``npm run dev`` in ./frontend",
    }
"@ | Out-File -FilePath "backend\main.py" -Encoding UTF8
    Write-Host "✓ Created backend\main.py" -ForegroundColor Green
} else {
    Write-Host "✓ backend\main.py already exists" -ForegroundColor Green
}

# Create missing __init__.py files
$initFiles = @(
    "backend\__init__.py",
    "backend\api\__init__.py",
    "backend\compute\__init__.py",
    "backend\loaders\__init__.py",
    "backend\scripts\__init__.py"
)

foreach ($file in $initFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "Creating $file..." -ForegroundColor Yellow
        New-Item -Path $file -ItemType File -Force | Out-Null
        Write-Host "✓ Created $file" -ForegroundColor Green
    } else {
        Write-Host "✓ $file already exists" -ForegroundColor Green
    }
}

Write-Host "`nTesting import..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -c "import backend.main; print('✓ Import successful')" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Fix complete! You can now start the server with:" -ForegroundColor Green
    Write-Host "  .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend" -ForegroundColor White
} else {
    Write-Host "`n✗ Import failed. Check the error message above." -ForegroundColor Red
}
```

Run it with:

```powershell
.\fix_backend.ps1
```

## Files Modified/Created

1. **backend/main.py** - Created (FastAPI application entry point)
2. **backend/__init__.py** - Created if missing (empty file)
3. **backend/api/__init__.py** - Created if missing (empty file)
4. **backend/compute/__init__.py** - Created if missing (empty file)
5. **backend/loaders/__init__.py** - Created if missing (empty file)
6. **backend/scripts/__init__.py** - Created if missing (empty file)

## No Changes Made To

- `backend/data/market.duckdb` - Your data is safe
- `backend/api/routes.py` - Unchanged
- `backend/config.py` - Unchanged
- All other backend modules - Unchanged
- Frontend code - Unchanged
