"""
Scanner API Routes
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import logging

from backend.scanner import (
    ScannerCriteria,
    ScannerResponse,
    run_scan_api,
    get_cached_results
)

logger = logging.getLogger(__name__)

scanner_router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@scanner_router.post("/scan", response_model=ScannerResponse)
async def scan_stocks(criteria: Optional[ScannerCriteria] = None):
    """
    Run stock scanner with given criteria.
    
    This will:
    1. Load universe from Excel file
    2. Download price data from Yahoo Finance
    3. Apply technical criteria
    4. Calculate RS scores and percentiles
    5. Save results to files
    
    Args:
        criteria: Scanner criteria (optional)
        
    Returns:
        ScannerResponse with results
    """
    try:
        logger.info("Starting scanner via API")
        response = run_scan_api(criteria)
        logger.info(f"Scanner completed: {response.count} stocks found")
        return response
    except Exception as e:
        logger.error(f"Scanner API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scanner failed: {str(e)}")


@scanner_router.get("/scan", response_model=ScannerResponse)
async def get_scan_results():
    """
    Get cached scanner results without running a new scan.
    
    Returns the latest results from the most recent scan.
    
    Returns:
        ScannerResponse with cached results
    """
    try:
        logger.info("Fetching cached scanner results")
        response = get_cached_results()
        logger.info(f"Loaded {response.count} cached results")
        return response
    except Exception as e:
        logger.error(f"Failed to load cached results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load results: {str(e)}")


@scanner_router.get("/status")
async def scanner_status():
    """
    Get scanner status and configuration.
    
    Returns:
        Dictionary with scanner status info
    """
    from backend.scanner import SCANNER_AVAILABLE
    from pathlib import Path
    
    # Check if universe file exists
    universe_file = Path("backend/data/universe.xlsx")
    universe_exists = universe_file.exists()
    
    # Check if output directory exists
    output_dir = Path("backend/data/scanner_output")
    output_exists = output_dir.exists()
    
    # Count results
    result_count = 0
    if output_exists:
        excel_files = list(output_dir.glob("scan_results_*.xlsx"))
        if excel_files:
            import pandas as pd
            latest = max(excel_files)
            try:
                df = pd.read_excel(latest)
                result_count = len(df)
            except:
                pass
    
    return {
        "scanner_available": SCANNER_AVAILABLE,
        "universe_file_exists": universe_exists,
        "universe_file_path": str(universe_file),
        "output_directory_exists": output_exists,
        "output_directory_path": str(output_dir),
        "cached_result_count": result_count
    }
