# verify_fix.ps1
# Quick verification that the backend startup fix is working
# Run this from D:\Automation\TradingAutomation

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backend Startup Fix Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allPassed = $true

# Test 1: Check file existence
Write-Host "Test 1: Checking required files..." -ForegroundColor Yellow
$requiredFiles = @(
    "backend\main.py",
    "backend\__init__.py",
    "backend\api\__init__.py",
    "backend\config.py",
    "backend\api\routes.py"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "  OK: $file" -ForegroundColor Green
    } else {
        Write-Host "  MISSING: $file" -ForegroundColor Red
        $allPassed = $false
    }
}

# Test 2: Test Python import
Write-Host ""
Write-Host "Test 2: Testing Python import..." -ForegroundColor Yellow
$importResult = & .\.venv\Scripts\python.exe -c "import backend.main; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Import successful" -ForegroundColor Green
} else {
    Write-Host "  Import failed" -ForegroundColor Red
    Write-Host "  Error: $importResult" -ForegroundColor Red
    $allPassed = $false
}

# Test 3: Check dependencies
Write-Host ""
Write-Host "Test 3: Checking dependencies..." -ForegroundColor Yellow
$depResult = & .\.venv\Scripts\python.exe -c "import fastapi, uvicorn, duckdb, pandas, numpy; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  All dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  Missing dependencies" -ForegroundColor Red
    Write-Host "  Run: .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt" -ForegroundColor Yellow
    $allPassed = $false
}

# Test 4: Check database
Write-Host ""
Write-Host "Test 4: Checking database..." -ForegroundColor Yellow
if (Test-Path "backend\data\market.duckdb") {
    $dbSize = (Get-Item "backend\data\market.duckdb").Length
    $dbSizeMB = [math]::Round($dbSize/1MB, 2)
    Write-Host "  Database exists ($dbSizeMB MB)" -ForegroundColor Green
} else {
    Write-Host "  Database not found (will be created on first run)" -ForegroundColor Yellow
}

# Final result
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "All checks passed!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "You can now start the backend server:" -ForegroundColor White
    Write-Host ""
    Write-Host "  .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} else {
    Write-Host "Some checks failed" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Run .\fix_backend.ps1 to fix the issues." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
