"""
API routes for the stock scanner.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.scanner import scan_stocks


router = APIRouter(prefix="/api/scanner", tags=["scanner"])


class ScanRequest(BaseModel):
    """Scanner request parameters."""
    benchmark_ticker: str = "^CRSLDX"
    min_close_vs_high: float = 0.80
    require_above_sma50: bool = True
    require_sma50_above_sma150: bool = True
    require_rising_sma200: bool = True
    require_rs_at_high: bool = True
    lookback_days: int = 252


class ScanResult(BaseModel):
    """Single scan result."""
    symbol: str
    name: str
    ticker: str
    close: float
    close_vs_high_252: float
    sma50: float | None
    sma150: float | None
    sma200: float | None
    rs: float | None
    rising_rs: bool
    passes_close_vs_high: bool
    passes_above_sma50: bool
    passes_sma50_above_sma150: bool
    passes_rising_sma200: bool
    passes_rs_at_high: bool


class ScanResponse(BaseModel):
    """Scanner response."""
    results: list[ScanResult]
    count: int
    benchmark: str
    criteria: dict


@router.post("/scan", response_model=ScanResponse)
def scan(request: ScanRequest) -> ScanResponse:
    """
    Scan stocks against technical criteria.
    
    Returns stocks that pass all enabled hard rules.
    """
    df = scan_stocks(
        benchmark_ticker=request.benchmark_ticker,
        min_close_vs_high=request.min_close_vs_high,
        require_above_sma50=request.require_above_sma50,
        require_sma50_above_sma150=request.require_sma50_above_sma150,
        require_rising_sma200=request.require_rising_sma200,
        require_rs_at_high=request.require_rs_at_high,
        lookback_days=request.lookback_days,
    )
    
    results = df.to_dict("records") if not df.empty else []
    
    return ScanResponse(
        results=results,
        count=len(results),
        benchmark=request.benchmark_ticker,
        criteria={
            "min_close_vs_high": request.min_close_vs_high,
            "require_above_sma50": request.require_above_sma50,
            "require_sma50_above_sma150": request.require_sma50_above_sma150,
            "require_rising_sma200": request.require_rising_sma200,
            "require_rs_at_high": request.require_rs_at_high,
            "lookback_days": request.lookback_days,
        },
    )


@router.get("/scan")
def scan_get(
    benchmark_ticker: str = Query("^CRSLDX"),
    min_close_vs_high: float = Query(0.80),
    require_above_sma50: bool = Query(True),
    require_sma50_above_sma150: bool = Query(True),
    require_rising_sma200: bool = Query(True),
    require_rs_at_high: bool = Query(True),
    lookback_days: int = Query(252),
) -> ScanResponse:
    """
    Scan stocks against technical criteria (GET method).
    """
    request = ScanRequest(
        benchmark_ticker=benchmark_ticker,
        min_close_vs_high=min_close_vs_high,
        require_above_sma50=require_above_sma50,
        require_sma50_above_sma150=require_sma50_above_sma150,
        require_rising_sma200=require_rising_sma200,
        require_rs_at_high=require_rs_at_high,
        lookback_days=lookback_days,
    )
    return scan(request)
