"""
Stock scanner with technical criteria.

The strategy lives in :mod:`backend.scanner.engine`:

1. ``close >= min_close_vs_high * max(close, lookback_days)`` (always applied)
2. ``close >= SMA(50)``                       (when ``require_above_sma50``)
3. ``SMA(50) >= SMA(150)``                    (when ``require_sma50_above_sma150``)
4. ``SMA(200)[t] > SMA(200)[t-20 sessions]``  (when ``require_rising_sma200``)
5. ``RS[t] >= max(RS, lookback_days)``        (when ``require_rs_at_high``)

``scan_stocks`` keeps the historical DataFrame-returning signature for callers
that only want the matches; :func:`run_scan` is the entry point used by the
HTTP API and additionally returns diagnostics (evaluated/skipped counts,
per-criterion pass counts, phase timings). Failures raise
:class:`ScannerError` subclasses rather than returning an empty frame.
"""

from __future__ import annotations

import pandas as pd

from backend import config
from backend.scanner.engine import (  # noqa: F401  (public API)
    CRITERION_LABELS,
    ScanOutcome,
    ScannerBusyError,
    ScannerDataError,
    ScannerError,
    ScannerRequestError,
    ScanSettings,
    run_scan,
    scan_slot,
)


def scan_stocks(
    benchmark_ticker: str = config.RS_BENCHMARKS[0][1],
    min_close_vs_high: float = 0.80,
    require_above_sma50: bool = True,
    require_sma50_above_sma150: bool = True,
    require_rising_sma200: bool = True,
    require_rs_at_high: bool = True,
    lookback_days: int = config.SCANNER_DEFAULT_LOOKBACK,
) -> pd.DataFrame:
    """
    Scan the universe and return the matching symbols as a DataFrame.

    Raises :class:`ScannerRequestError` (bad parameters/benchmark) or
    :class:`ScannerDataError` (missing or unusable market data) instead of
    returning an empty frame that could be mistaken for "no matches".
    """
    settings = ScanSettings(
        benchmark_ticker=benchmark_ticker,
        min_close_vs_high=min_close_vs_high,
        require_above_sma50=require_above_sma50,
        require_sma50_above_sma150=require_sma50_above_sma150,
        require_rising_sma200=require_rising_sma200,
        require_rs_at_high=require_rs_at_high,
        lookback_days=lookback_days,
    )
    return run_scan(settings).frame


__all__ = [
    "CRITERION_LABELS",
    "ScanOutcome",
    "ScanSettings",
    "ScannerBusyError",
    "ScannerDataError",
    "ScannerError",
    "ScannerRequestError",
    "run_scan",
    "scan_slot",
    "scan_stocks",
]
