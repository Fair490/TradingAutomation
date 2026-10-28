"""
Stock Scanner - API Integration
This module integrates the scanner with the FastAPI backend.
"""

import pandas as pd
from typing import List, Optional, Dict
from pydantic import BaseModel
from pathlib import Path
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import the scanner module
try:
    from backend.scanner.scanner_v2 import run_scanner as run_full_scanner
    SCANNER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Scanner module not available: {e}")
    SCANNER_AVAILABLE = False


class ScannerCriteria(BaseModel):
    """Scanner criteria configuration."""
    ema_fast: int = 50
    ema_slow: int = 150
    high_lookback: int = 260
    high_threshold: float = 0.70
    rs_lookback: int = 126
    min_bars: int = 260
    benchmark: str = "^CRSLDX"


class ScannerResult(BaseModel):
    """Single scanner result."""
    rank: int
    symbol: str
    name: str = ""
    close: float
    ema50: float
    ema150: float
    high_52w: float
    rs_ratio: float
    rs_score_pct: float
    rs_percentile: int
    proximity_pct: float = 0.0
    proximity_percentile: int = 0
    composite_score: float = 0.0
    extension_pct: float = 0.0
    extended: bool = False


class ScannerResponse(BaseModel):
    """Scanner API response."""
    results: List[ScannerResult]
    count: int
    timestamp: str
    criteria: ScannerCriteria
    total_scanned: int
    passed: int
    skipped: int


def get_latest_results() -> Optional[pd.DataFrame]:
    """Get the latest scan results from file."""
    output_dir = Path("backend/data/scanner_output")
    if not output_dir.exists():
        return None
    
    # Find latest Excel file
    excel_files = list(output_dir.glob("scan_results_*.xlsx"))
    if not excel_files:
        return None
    
    latest_file = max(excel_files, key=lambda f: f.stat().st_mtime)
    
    try:
        df = pd.read_excel(latest_file)
        return df
    except Exception as e:
        logger.error(f"Error loading results: {e}")
        return None


def run_scan_api(criteria: Optional[ScannerCriteria] = None) -> ScannerResponse:
    """
    Run the scanner and return results for API.
    
    Args:
        criteria: Scanner criteria (optional, uses defaults if not provided)
        
    Returns:
        ScannerResponse with results
    """
    if not SCANNER_AVAILABLE:
        return ScannerResponse(
            results=[],
            count=0,
            timestamp=datetime.now().isoformat(),
            criteria=criteria or ScannerCriteria(),
            total_scanned=0,
            passed=0,
            skipped=0
        )
    
    try:
        # Run the full scanner
        results_df = run_full_scanner()
        
        if results_df.empty:
            return ScannerResponse(
                results=[],
                count=0,
                timestamp=datetime.now().isoformat(),
                criteria=criteria or ScannerCriteria(),
                total_scanned=0,
                passed=0,
                skipped=0
            )
        
        # Convert to ScannerResult objects
        scanner_results = []
        for _, row in results_df.iterrows():
            scanner_results.append(
                ScannerResult(
                    rank=int(row['Rank']),
                    symbol=row['Symbol'],
                    name="",  # Could be populated from universe file
                    close=float(row['Close']),
                    ema50=float(row['EMA50']),
                    ema150=float(row['EMA150']),
                    high_52w=float(row['52W_High']),
                    rs_ratio=float(row['RS_Ratio']),
                    rs_score_pct=float(row['RS_Score_Pct']),
                    rs_percentile=int(row['RS_Percentile']),
                    proximity_pct=float(row.get('Proximity_Pct', 0.0)),
                    proximity_percentile=int(row.get('Proximity_Percentile', 0)),
                    composite_score=float(row.get('Composite_Score', 0.0)),
                    extension_pct=float(row.get('Extension_Pct', 0.0)),
                    extended=bool(row.get('Extended', False))
                )
            )
        
        return ScannerResponse(
            results=scanner_results,
            count=len(scanner_results),
            timestamp=datetime.now().isoformat(),
            criteria=criteria or ScannerCriteria(),
            total_scanned=len(results_df),
            passed=len(scanner_results),
            skipped=0
        )
        
    except Exception as e:
        logger.error(f"Scanner failed: {e}", exc_info=True)
        return ScannerResponse(
            results=[],
            count=0,
            timestamp=datetime.now().isoformat(),
            criteria=criteria or ScannerCriteria(),
            total_scanned=0,
            passed=0,
            skipped=0
        )


def get_cached_results() -> ScannerResponse:
    """Get cached results from file without running scanner."""
    df = get_latest_results()
    
    if df is None or df.empty:
        return ScannerResponse(
            results=[],
            count=0,
            timestamp=datetime.now().isoformat(),
            criteria=ScannerCriteria(),
            total_scanned=0,
            passed=0,
            skipped=0
        )
    
    # Convert to ScannerResult objects
    scanner_results = []
    for _, row in df.iterrows():
        scanner_results.append(
            ScannerResult(
                rank=int(row['Rank']),
                symbol=row['Symbol'],
                name="",
                close=float(row['Close']),
                ema50=float(row['EMA50']),
                ema150=float(row['EMA150']),
                high_52w=float(row['52W_High']),
                rs_ratio=float(row['RS_Ratio']),
                rs_score_pct=float(row['RS_Score_Pct']),
                rs_percentile=int(row['RS_Percentile']),
                proximity_pct=float(row.get('Proximity_Pct', 0.0)),
                proximity_percentile=int(row.get('Proximity_Percentile', 0)),
                composite_score=float(row.get('Composite_Score', 0.0)),
                extension_pct=float(row.get('Extension_Pct', 0.0)),
                extended=bool(row.get('Extended', False))
            )
        )
    
    return ScannerResponse(
        results=scanner_results,
        count=len(scanner_results),
        timestamp=datetime.now().isoformat(),
        criteria=ScannerCriteria(),
        total_scanned=len(scanner_results),
        passed=len(scanner_results),
        skipped=0
    )
