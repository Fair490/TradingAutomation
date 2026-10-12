"""
API routes for the stock scanner.

Contract
--------
``POST /api/scanner/scan`` (and its GET twin) runs the strategy and returns the
matching symbols plus diagnostics. Status codes are meaningful:

* 200 - the scan ran; ``results`` may legitimately be empty and then
  ``diagnostics.explanation`` says why.
* 400 - the request cannot be satisfied (unknown benchmark, bad parameters).
* 409 - another scan is already running.
* 422 - the request body does not match the schema (FastAPI/pydantic).
* 500 - unexpected internal failure (logged with a traceback).
* 503 - required market data is missing/empty/unreadable. This is deliberately
  NOT a 200 with an empty list: a data failure must never look like a
  legitimate zero-match scan.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend import config
from backend.scanner import (
    ScanOutcome,
    ScannerBusyError,
    ScannerDataError,
    ScannerError,
    ScannerRequestError,
    ScanSettings,
    run_scan,
    scan_slot,
)

log = logging.getLogger("market-health.scanner.api")

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


# --------------------------------------------------------------------------- #
# Request / response models (these double as the frontend contract)
# --------------------------------------------------------------------------- #
class ScanRequest(BaseModel):
    """Scanner request parameters."""

    benchmark_ticker: str = Field(
        default=config.RS_BENCHMARKS[0][1],
        min_length=1,
        max_length=32,
        description="Index ticker used for relative strength",
    )
    min_close_vs_high: float = Field(
        default=0.80,
        gt=0,
        le=1.0,
        description="Minimum close / lookback-high ratio, e.g. 0.80 for 80%",
    )
    require_above_sma50: bool = True
    require_sma50_above_sma150: bool = True
    require_rising_sma200: bool = True
    require_rs_at_high: bool = True
    lookback_days: int = Field(
        default=config.SCANNER_DEFAULT_LOOKBACK,
        ge=config.SCANNER_MIN_LOOKBACK,
        le=config.SCANNER_MAX_LOOKBACK,
        description="Lookback window in trading sessions",
    )

    def to_settings(self) -> ScanSettings:
        return ScanSettings(
            benchmark_ticker=self.benchmark_ticker,
            min_close_vs_high=self.min_close_vs_high,
            require_above_sma50=self.require_above_sma50,
            require_sma50_above_sma150=self.require_sma50_above_sma150,
            require_rising_sma200=self.require_rising_sma200,
            require_rs_at_high=self.require_rs_at_high,
            lookback_days=self.lookback_days,
        )


class ScanResult(BaseModel):
    """Single scan result."""

    symbol: str
    name: str
    ticker: str
    close: float
    close_vs_high_252: float | None = None
    sma50: float | None = None
    sma150: float | None = None
    sma200: float | None = None
    rs: float | None = None
    rising_rs: bool = False
    passes_close_vs_high: bool = False
    passes_above_sma50: bool = False
    passes_sma50_above_sma150: bool = False
    passes_rising_sma200: bool = False
    passes_rs_at_high: bool = False


class SkippedSymbol(BaseModel):
    ticker: str
    symbol: str
    reason: str


class ScanDiagnostics(BaseModel):
    """Everything needed to explain what a scan did."""

    universe_size: int
    symbols_with_data: int
    symbols_evaluated: int
    symbols_matched: int
    symbols_skipped: int
    skipped: dict[str, int] = {}
    skipped_symbols: list[SkippedSymbol] = []
    criterion_pass_counts: dict[str, int] = {}
    criterion_active: dict[str, bool] = {}
    benchmark: str
    benchmark_name: str | None = None
    benchmark_first_date: str | None = None
    benchmark_last_date: str | None = None
    benchmark_sessions: int = 0
    evaluation_date: str | None = None
    required_sessions: int = 0
    lookback_days: int = 0
    price_column: str = "close"
    invalid_price_rows: int = 0
    symbols_with_invalid_prices: int = 0
    timings_ms: dict[str, float] = {}
    warnings: list[str] = []
    explanation: str = ""


class ScanResponse(BaseModel):
    """Scanner response."""

    results: list[ScanResult]
    count: int
    benchmark: str
    criteria: dict
    diagnostics: ScanDiagnostics


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _criteria_payload(settings: ScanSettings) -> dict:
    return {
        "min_close_vs_high": settings.min_close_vs_high,
        "require_above_sma50": settings.require_above_sma50,
        "require_sma50_above_sma150": settings.require_sma50_above_sma150,
        "require_rising_sma200": settings.require_rising_sma200,
        "require_rs_at_high": settings.require_rs_at_high,
        "lookback_days": settings.lookback_days,
    }


def _execute(settings: ScanSettings) -> ScanResponse:
    """
    Run one scan and translate scanner failures into HTTP status codes.

    The time spent turning the result frame into response records is reported
    back as ``response_serialization`` in ``diagnostics.timings_ms``.
    """
    try:
        with scan_slot():
            outcome: ScanOutcome = run_scan(settings)
    except ScannerRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.payload()) from exc
    except ScannerBusyError as exc:
        raise HTTPException(status_code=409, detail=exc.payload()) from exc
    except ScannerDataError as exc:
        raise HTTPException(status_code=503, detail=exc.payload()) from exc
    except ScannerError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.payload()) from exc
    except HTTPException:
        raise
    except Exception as exc:  # unexpected: log it, tell the client nothing internal
        log.exception("scanner: unexpected failure")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "internal_error",
                "message": (
                    "The scanner failed unexpectedly. The backend log has the "
                    f"traceback (reference: {type(exc).__name__})."
                ),
            },
        ) from exc

    started = time.perf_counter()
    frame = outcome.frame
    records = frame.to_dict("records") if not frame.empty else []
    serialize_ms = (time.perf_counter() - started) * 1000.0

    diagnostics = dict(outcome.diagnostics)
    diagnostics["timings_ms"] = {
        **diagnostics.get("timings_ms", {}),
        "response_serialization": round(serialize_ms, 1),
    }
    return ScanResponse(
        results=records,
        count=len(records),
        benchmark=settings.benchmark_ticker,
        criteria=_criteria_payload(settings),
        diagnostics=ScanDiagnostics(**diagnostics),
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post(
    "/scan",
    response_model=ScanResponse,
    responses={
        400: {"description": "Unsupported benchmark or parameters"},
        409: {"description": "A scan is already running"},
        500: {"description": "Unexpected internal failure"},
        503: {"description": "Required market data is missing or unreadable"},
    },
)
def scan(request: ScanRequest) -> ScanResponse:
    """
    Scan stocks against the technical criteria.

    Returns the symbols passing every active rule, plus diagnostics covering
    universe size, evaluated/skipped symbols, per-criterion pass counts and
    per-phase timings.
    """
    settings = request.to_settings().validate()
    return _execute(settings)


@router.get(
    "/scan",
    response_model=ScanResponse,
    responses={
        400: {"description": "Unsupported benchmark or parameters"},
        409: {"description": "A scan is already running"},
        500: {"description": "Unexpected internal failure"},
        503: {"description": "Required market data is missing or unreadable"},
    },
)
def scan_get(
    benchmark_ticker: str = Query(
        default=config.RS_BENCHMARKS[0][1],
        min_length=1,
        max_length=32,
        description="Index ticker used for relative strength",
    ),
    min_close_vs_high: float = Query(
        default=0.80, gt=0, le=1.0, description="Minimum close / lookback-high ratio"
    ),
    require_above_sma50: bool = Query(True),
    require_sma50_above_sma150: bool = Query(True),
    require_rising_sma200: bool = Query(True),
    require_rs_at_high: bool = Query(True),
    lookback_days: int = Query(
        default=config.SCANNER_DEFAULT_LOOKBACK,
        ge=config.SCANNER_MIN_LOOKBACK,
        le=config.SCANNER_MAX_LOOKBACK,
    ),
) -> ScanResponse:
    """GET twin of ``POST /api/scanner/scan`` (handy for curl/debugging)."""
    settings = ScanSettings(
        benchmark_ticker=benchmark_ticker,
        min_close_vs_high=min_close_vs_high,
        require_above_sma50=require_above_sma50,
        require_sma50_above_sma150=require_sma50_above_sma150,
        require_rising_sma200=require_rising_sma200,
        require_rs_at_high=require_rs_at_high,
        lookback_days=lookback_days,
    ).validate()
    return _execute(settings)
