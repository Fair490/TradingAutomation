"""
Vectorised stock-scanner engine.

Strategy (unchanged - see ``run_scan`` for the definitions and defaults):

1. ``close >= min_close_vs_high * max(close, lookback_days)`` (always applied)
2. ``close >= SMA(50)``                       (when ``require_above_sma50``)
3. ``SMA(50) >= SMA(150)``                    (when ``require_sma50_above_sma150``)
4. ``SMA(200)[t] > SMA(200)[t-20 sessions]``  (when ``require_rising_sma200``)
5. ``RS[t] >= max(RS, lookback_days)``        (when ``require_rs_at_high``)
   where ``RS = close / benchmark_close * 100`` with the benchmark aligned by
   forward-filling it onto the stock's own sessions.

Every window is measured in trading sessions (rows in ``prices``), exactly as
before; the benchmark-relative series is built once per scan instead of once
per symbol.

Deliberate differences from the original implementation - all conservative or
neutral, never a loosened filter:

* Data for the whole universe is read with a single query and every indicator
  is computed once across a (dates x tickers) matrix. The DuckDB lock is held
  for one short read instead of for the entire scan, so a scan no longer
  blocks unrelated API requests.
* Rolling windows use ``min_periods = window``. The original used
  ``min_periods = 1`` for the rolling highs; combined with its explicit "at
  least ``lookback_days`` rows" gate that produced identical answers for
  complete histories, but a hole in the data could manufacture a false
  "at the high" pass. A full window is now required.
* Symbols with too little history, symbols with no usable prices and stale
  symbols are counted and reported instead of being dropped silently.
* A symbol is still evaluated as of its own latest valid session, so a stock
  that did not trade on the newest date is judged on its last bar - unless
  that bar is older than ``SCANNER_MAX_STALENESS_SESSIONS`` sessions, in which
  case it is skipped and reported.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import numpy as np
import pandas as pd

from backend import config
from backend.loaders import store
from backend.loaders.universe import Constituent, load_universe

log = logging.getLogger("market-health.scanner")

# --------------------------------------------------------------------------- #
# Skip reasons reported in the diagnostics payload
# --------------------------------------------------------------------------- #
SKIP_NO_DATA = "no_price_history"
SKIP_INVALID_PRICES = "invalid_prices"
SKIP_INSUFFICIENT_HISTORY = "insufficient_history"
SKIP_STALE = "stale_data"

CRITERION_CLOSE_VS_HIGH = "close_vs_high"
CRITERION_ABOVE_SMA50 = "above_sma50"
CRITERION_SMA50_ABOVE_SMA150 = "sma50_above_sma150"
CRITERION_RISING_SMA200 = "rising_sma200"
CRITERION_RS_AT_HIGH = "rs_at_high"

CRITERION_LABELS = {
    CRITERION_CLOSE_VS_HIGH: "close vs lookback high",
    CRITERION_ABOVE_SMA50: "close >= 50DMA",
    CRITERION_SMA50_ABOVE_SMA150: "50DMA >= 150DMA",
    CRITERION_RISING_SMA200: "200DMA rising",
    CRITERION_RS_AT_HIGH: "RS at lookback high",
}

RESULT_COLUMNS = [
    "symbol",
    "name",
    "ticker",
    "close",
    "close_vs_high_252",
    "sma50",
    "sma150",
    "sma200",
    "rs",
    "rising_rs",
    "passes_close_vs_high",
    "passes_above_sma50",
    "passes_sma50_above_sma150",
    "passes_rising_sma200",
    "passes_rs_at_high",
]


# --------------------------------------------------------------------------- #
# Errors - the route layer maps these onto HTTP status codes
# --------------------------------------------------------------------------- #
class ScannerError(Exception):
    """Base class for scanner failures that carry a machine-readable code."""

    code = "scanner_error"
    http_status = 500

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code

    def payload(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class ScannerRequestError(ScannerError):
    """The caller asked for something that cannot be scanned (HTTP 400)."""

    code = "invalid_request"
    http_status = 400


class ScannerDataError(ScannerError):
    """Required data is missing, empty or unreadable (HTTP 503)."""

    code = "data_unavailable"
    http_status = 503


class ScannerBusyError(ScannerError):
    """A scan is already running (HTTP 409)."""

    code = "scan_in_progress"
    http_status = 409


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ScanSettings:
    """Scan parameters, mirroring the request model in ``routes.py``."""

    benchmark_ticker: str = config.RS_BENCHMARKS[0][1]
    min_close_vs_high: float = 0.80
    require_above_sma50: bool = True
    require_sma50_above_sma150: bool = True
    require_rising_sma200: bool = True
    require_rs_at_high: bool = True
    lookback_days: int = config.SCANNER_DEFAULT_LOOKBACK
    price_column: str = config.SCANNER_PRICE_COLUMN

    def active_criteria(self) -> dict[str, bool]:
        return {
            CRITERION_CLOSE_VS_HIGH: True,  # the threshold input *is* the rule
            CRITERION_ABOVE_SMA50: self.require_above_sma50,
            CRITERION_SMA50_ABOVE_SMA150: self.require_sma50_above_sma150,
            CRITERION_RISING_SMA200: self.require_rising_sma200,
            CRITERION_RS_AT_HIGH: self.require_rs_at_high,
        }

    def required_sessions(self) -> int:
        """
        Sessions a symbol needs before it can be evaluated at all.

        This is the original "at least ``lookback_days`` rows" gate widened to
        whatever the *enabled* criteria actually need (a 20-session lookback
        difference on a 200-session average needs 220 rows). Symbols below the
        bar are reported as skipped instead of silently failing every filter.
        """
        needed = self.lookback_days
        if self.require_above_sma50:
            needed = max(needed, config.SCANNER_SMA_FAST)
        if self.require_sma50_above_sma150:
            needed = max(needed, config.SCANNER_SMA_MID)
        if self.require_rising_sma200:
            needed = max(
                needed,
                config.SCANNER_SMA_SLOW + config.SCANNER_SMA200_RISING_OFFSET,
            )
        return needed

    def validate(self) -> "ScanSettings":
        """Raise :class:`ScannerRequestError` for anything unsupported."""
        if not str(self.benchmark_ticker or "").strip():
            raise ScannerRequestError("A benchmark ticker is required.")
        if not (0.0 < float(self.min_close_vs_high) <= 1.0):
            raise ScannerRequestError(
                "min_close_vs_high must be a ratio between 0 and 1 "
                f"(got {self.min_close_vs_high}); the UI sends 0.80 for 80%.",
                code="invalid_min_close_vs_high",
            )
        lookback = int(self.lookback_days)
        if not (config.SCANNER_MIN_LOOKBACK <= lookback <= config.SCANNER_MAX_LOOKBACK):
            raise ScannerRequestError(
                "lookback_days must be between "
                f"{config.SCANNER_MIN_LOOKBACK} and {config.SCANNER_MAX_LOOKBACK} "
                f"sessions (got {self.lookback_days}).",
                code="invalid_lookback_days",
            )
        if self.price_column not in ("close", "adj_close"):
            raise ScannerRequestError(
                f"Unsupported price column '{self.price_column}'.",
                code="invalid_price_column",
            )
        return self


# --------------------------------------------------------------------------- #
# Outcome containers
# --------------------------------------------------------------------------- #
@dataclass
class ScanOutcome:
    """Matching symbols plus everything needed to explain the scan."""

    frame: pd.DataFrame
    diagnostics: dict = field(default_factory=dict)


class SymbolStatus:
    """Per-symbol classification computed before the criteria are applied."""

    def __init__(self, tickers: list[str], reason_by_ticker: dict[str, str]) -> None:
        self.reason_by_ticker = reason_by_ticker
        self.skipped_examples = [
            (ticker, reason_by_ticker[ticker])
            for ticker in tickers
            if ticker in reason_by_ticker
        ]
        self.counts: dict[str, int] = {}
        for ticker in tickers:
            reason = reason_by_ticker.get(ticker)
            if reason:
                self.counts[reason] = self.counts.get(reason, 0) + 1

    def is_skipped(self, ticker: str) -> bool:
        return ticker in self.reason_by_ticker


# --------------------------------------------------------------------------- #
# Concurrency guard
# --------------------------------------------------------------------------- #
_SCAN_SLOT = threading.BoundedSemaphore(1)


@contextmanager
def scan_slot() -> Iterator[None]:
    """
    Allow one scan at a time.

    Two concurrent scans of the same universe do identical work and compete for
    the same DuckDB connection, so a second caller gets a clear 409 instead of
    queueing up behind the first.
    """
    if not _SCAN_SLOT.acquire(blocking=False):
        raise ScannerBusyError(
            "A scan is already running. Wait for it to finish and try again."
        )
    try:
        yield
    finally:
        _SCAN_SLOT.release()


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def load_universe_or_raise() -> list[Constituent]:
    """Load the configured universe, mapping file problems to data errors."""
    try:
        universe = load_universe()
    except FileNotFoundError as exc:
        raise ScannerDataError(
            "The stock universe file could not be found. Add the Nifty Total "
            "Market constituents CSV and retry.",
            code="universe_unavailable",
        ) from exc
    except (ValueError, OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ScannerDataError(
            f"The stock universe could not be read: {exc}",
            code="universe_unavailable",
        ) from exc
    if not universe:
        raise ScannerDataError(
            "The stock universe file is empty - there is nothing to scan.",
            code="universe_unavailable",
        )
    return universe


def _benchmark_name(ticker: str) -> str | None:
    for name, candidate in (*config.RS_BENCHMARKS, *config.INDEX_CANDIDATES):
        if candidate == ticker:
            return name
    return None


def _benchmark_error(settings: ScanSettings, known: dict[str, str]) -> ScannerError:
    """
    Tickers the app supports but has no data for -> 503 (refresh needed).
    Anything else -> 400 (the request asked for something we do not track).
    """
    accepted = {ticker for _, ticker in config.RS_BENCHMARKS}
    accepted |= {ticker for _, ticker in config.INDEX_CANDIDATES}
    if settings.benchmark_ticker in known or settings.benchmark_ticker in accepted:
        return ScannerDataError(
            f"The benchmark '{settings.benchmark_ticker}' has no stored price "
            "history. Run a data refresh before scanning.",
            code="benchmark_unavailable",
        )
    supported = ", ".join(ticker for _, ticker in config.RS_BENCHMARKS)
    return ScannerRequestError(
        f"Unknown benchmark '{settings.benchmark_ticker}'. Supported benchmarks: "
        f"{supported}.",
        code="unknown_benchmark",
    )


def _load_benchmark(settings: ScanSettings, known: dict[str, str]) -> pd.DataFrame:
    """Benchmark closes, validated and sorted; raises when unusable."""
    with store.session() as con:
        frame = store.load_series(con, settings.benchmark_ticker)
    if frame.empty:
        raise _benchmark_error(settings, known)

    frame = frame[["date", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"])
    values = frame["close"].to_numpy(dtype="float64")
    frame = frame[np.isfinite(values) & (values > 0)]
    frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    if frame.empty:
        raise _benchmark_error(settings, known)
    return frame.reset_index(drop=True)


def _load_panel(settings: ScanSettings, tickers: list[str]) -> pd.DataFrame:
    """All universe prices in one query (not one query per symbol)."""
    try:
        with store.session() as con:
            panel = store.load_price_panel(con, tickers, column=settings.price_column)
    except Exception as exc:  # duckdb.Error and friends
        log.exception("scanner: price panel load failed")
        raise ScannerDataError(
            "The market database could not be read. Check the backend log for "
            "details and retry.",
            code="database_error",
        ) from exc
    if panel.empty:
        return panel
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    panel["value"] = pd.to_numeric(panel["value"], errors="coerce")
    panel = panel.drop_duplicates(subset=["ticker", "date"], keep="last")
    return panel.sort_values(["ticker", "date"])


# --------------------------------------------------------------------------- #
# Indicator maths (pure, so it can be unit tested without a database)
# --------------------------------------------------------------------------- #
def positions_from_end(mask: np.ndarray, n_from_end: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Row position of the ``n_from_end``-th valid observation from the end.

    ``n_from_end=1`` is each column's last valid entry. Positions count
    *observations*, not rows, so a column with gaps behaves exactly like the
    original per-symbol slicing. Columns with fewer valid entries than
    requested get position ``-1`` and ``enough=False``.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("mask must be 2-D (rows x tickers)")
    reversed_cum = np.cumsum(mask[::-1], axis=0)
    enough = reversed_cum[-1] >= n_from_end
    found = np.argmax(reversed_cum >= n_from_end, axis=0)
    positions = (mask.shape[0] - 1) - found
    return np.where(enough, positions, -1), enough


def _gather(matrix: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Take one value per column at the given row positions (NaN when -1)."""
    safe = np.where(positions >= 0, positions, 0)
    values = np.take_along_axis(matrix, safe[None, :], axis=0)[0]
    return np.where(positions >= 0, values, np.nan)


def compute_indicators(
    close: pd.DataFrame,
    benchmark_close: pd.Series,
    lookback_days: int,
) -> dict:
    """
    Every indicator the scanner needs, computed once for the whole matrix.

    ``close`` is a (dates x tickers) frame of valid closes, ``benchmark_close``
    a series on the same date index. Returns aligned matrices plus the trailing
    value of each indicator per symbol and the "value N sessions back" values.
    """
    if close.empty:
        raise ValueError("close matrix is empty")

    sma_fast = close.rolling(
        config.SCANNER_SMA_FAST, min_periods=config.SCANNER_SMA_FAST
    ).mean()
    sma_mid = close.rolling(
        config.SCANNER_SMA_MID, min_periods=config.SCANNER_SMA_MID
    ).mean()
    sma_slow = close.rolling(
        config.SCANNER_SMA_SLOW, min_periods=config.SCANNER_SMA_SLOW
    ).mean()
    highest = close.rolling(lookback_days, min_periods=lookback_days).max()

    # RS = close / benchmark * 100 with the benchmark forward-filled onto the
    # stock sessions (identical to the original per-symbol reindex-ffill, done
    # once for the whole universe).
    aligned_benchmark = benchmark_close.reindex(close.index).ffill()
    rs = close.div(aligned_benchmark, axis=0) * 100.0
    rs_highest = rs.rolling(lookback_days, min_periods=lookback_days).max()

    close_values = close.to_numpy(dtype="float64")
    sma_fast_values = sma_fast.to_numpy(dtype="float64")
    sma_mid_values = sma_mid.to_numpy(dtype="float64")
    sma_slow_values = sma_slow.to_numpy(dtype="float64")
    highest_values = highest.to_numpy(dtype="float64")
    rs_values = rs.to_numpy(dtype="float64")
    rs_highest_values = rs_highest.to_numpy(dtype="float64")
    rs_valid = np.isfinite(rs_values)

    steps_back = config.SCANNER_SMA200_RISING_OFFSET + 1
    last_pos, has_any = positions_from_end(np.isfinite(close_values), 1)
    back_sma_pos, has_sma_back = positions_from_end(np.isfinite(sma_slow_values), steps_back)
    back_rs_pos, has_rs_back = positions_from_end(rs_valid, steps_back)

    return {
        "close": close,
        "sma_fast": sma_fast,
        "sma_mid": sma_mid,
        "sma_slow": sma_slow,
        "highest": highest,
        "rs": rs,
        "rs_highest": rs_highest,
        "last_pos": last_pos,
        "has_any": has_any,
        "last_close": _gather(close_values, last_pos),
        "sma_fast_last": _gather(sma_fast_values, last_pos),
        "sma_mid_last": _gather(sma_mid_values, last_pos),
        "sma_slow_last": _gather(sma_slow_values, last_pos),
        "sma_slow_back": _gather(sma_slow_values, back_sma_pos),
        "has_sma_back": has_sma_back,
        "highest_last": _gather(highest_values, last_pos),
        "rs_last": _gather(rs_values, last_pos),
        "rs_back": _gather(rs_values, back_rs_pos),
        "has_rs_back": has_rs_back,
        "rs_highest_last": _gather(rs_highest_values, last_pos),
        "sessions": np.isfinite(close_values).sum(axis=0),
        "rs_sessions": rs_valid.sum(axis=0),
    }


# --------------------------------------------------------------------------- #
# Symbol classification + criteria
# --------------------------------------------------------------------------- #
def classify_symbols(
    universe_tickers: list[str],
    raw_counts: pd.Series,
    clean_counts: pd.Series,
    session_counts: dict[str, int],
    staleness: dict[str, int],
    required_sessions: int,
    max_staleness: int,
) -> SymbolStatus:
    """
    Decide, per universe symbol, whether it can be evaluated and why not.

    ``raw_counts`` counts stored rows per ticker, ``clean_counts`` counts rows
    with a usable price, ``session_counts`` the valid sessions that reached the
    matrix and ``staleness`` how many sessions behind the newest bar the
    symbol's last bar is.
    """
    reason_by_ticker: dict[str, str] = {}
    for ticker in universe_tickers:
        if ticker not in raw_counts.index or raw_counts[ticker] <= 0:
            reason_by_ticker[ticker] = SKIP_NO_DATA
        elif clean_counts.get(ticker, 0) <= 0:
            reason_by_ticker[ticker] = SKIP_INVALID_PRICES
        elif session_counts.get(ticker, 0) < required_sessions:
            reason_by_ticker[ticker] = SKIP_INSUFFICIENT_HISTORY
        elif staleness.get(ticker, 0) > max_staleness:
            reason_by_ticker[ticker] = SKIP_STALE
    return SymbolStatus(universe_tickers, reason_by_ticker)


def apply_criteria(indicators: dict, settings: ScanSettings) -> dict[str, np.ndarray]:
    """
    Each criterion on its own, over every column of the matrix.

    NaN makes a comparison False, so a symbol without the required history
    simply fails rather than crashing. Criteria are evaluated independently
    first - that is what makes the per-filter pass counts honest - and only
    then combined with AND.
    """
    last_close = indicators["last_close"]
    highest_last = indicators["highest_last"]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(
            (highest_last > 0) & np.isfinite(last_close),
            last_close / highest_last,
            np.nan,
        )
    return {
        CRITERION_CLOSE_VS_HIGH: ratio >= float(settings.min_close_vs_high),
        CRITERION_ABOVE_SMA50: indicators["sma_fast_last"] <= last_close,
        CRITERION_SMA50_ABOVE_SMA150: (
            indicators["sma_mid_last"] <= indicators["sma_fast_last"]
        ),
        CRITERION_RISING_SMA200: np.asarray(indicators["has_sma_back"], dtype=bool)
        & (indicators["sma_slow_back"] < indicators["sma_slow_last"]),
        CRITERION_RS_AT_HIGH: (
            indicators["rs_sessions"] >= settings.lookback_days
        )
        & (indicators["rs_last"] >= indicators["rs_highest_last"]),
    }


def _result_rows(
    indicators: dict,
    passes: dict[str, np.ndarray],
    selected: np.ndarray,
    tickers: list[str],
    symbols: dict[str, str],
    names: dict[str, str],
) -> pd.DataFrame:
    """Build the result frame from boolean masks (no per-symbol SQL)."""
    chosen = np.flatnonzero(selected)
    rows = []
    for index in chosen:
        ticker = tickers[index]

        def _round(value: float) -> float | None:
            return None if not np.isfinite(value) else round(float(value), 2)

        close_value = indicators["last_close"][index]
        rs_value = indicators["rs_last"][index]
        rs_back = indicators["rs_back"][index]
        rows.append(
            {
                "symbol": symbols.get(ticker, ticker),
                "name": names.get(ticker, ticker),
                "ticker": ticker,
                "close": float(close_value),
                "close_vs_high_252": _round(
                    indicators["last_close"][index]
                    / indicators["highest_last"][index]
                    * 100.0
                    if indicators["highest_last"][index] > 0
                    else np.nan
                ),
                "sma50": _round(indicators["sma_fast_last"][index]),
                "sma150": _round(indicators["sma_mid_last"][index]),
                "sma200": _round(indicators["sma_slow_last"][index]),
                "rs": _round(rs_value),
                "rising_rs": bool(
                    indicators["has_rs_back"][index]
                    and np.isfinite(rs_back)
                    and np.isfinite(rs_value)
                    and rs_value > rs_back
                ),
                "passes_close_vs_high": bool(passes[CRITERION_CLOSE_VS_HIGH][index]),
                "passes_above_sma50": bool(passes[CRITERION_ABOVE_SMA50][index]),
                "passes_sma50_above_sma150": bool(
                    passes[CRITERION_SMA50_ABOVE_SMA150][index]
                ),
                "passes_rising_sma200": bool(passes[CRITERION_RISING_SMA200][index]),
                "passes_rs_at_high": bool(passes[CRITERION_RS_AT_HIGH][index]),
            }
        )
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


# --------------------------------------------------------------------------- #
# The scan itself
# --------------------------------------------------------------------------- #
def run_scan(settings: ScanSettings | None = None) -> ScanOutcome:
    """
    Run one scan.

    Raises :class:`ScannerError` subclasses for missing data or unsupported
    requests instead of returning an empty result that hides a failure, and
    holds the database lock only for short reads.
    """
    settings = (settings or ScanSettings()).validate()
    timings: dict[str, float] = {}
    started = time.perf_counter()

    # ---- universe -------------------------------------------------------- #
    t0 = time.perf_counter()
    universe = load_universe_or_raise()
    tickers = [c.ticker for c in universe]
    symbols = {c.ticker: c.symbol for c in universe}
    names = {c.ticker: c.name for c in universe}
    timings["universe"] = time.perf_counter() - t0

    # ---- database readiness + benchmark ---------------------------------- #
    t0 = time.perf_counter()
    try:
        with store.session() as con:
            total_prices = store.count_prices(con)
            known = store.known_ticker_rows(con)
    except Exception as exc:
        log.exception("scanner: database readiness check failed")
        raise ScannerDataError(
            "The market database could not be read. Check the backend log for "
            "details and retry.",
            code="database_error",
        ) from exc
    if total_prices <= 0:
        raise ScannerDataError(
            "The market database has no price history yet. Run a data refresh "
            "from the dashboard first, then scan.",
            code="empty_database",
        )

    benchmark = _load_benchmark(settings, known)
    timings["benchmark"] = time.perf_counter() - t0

    # ---- price panel (one query for the whole universe) ------------------- #
    t0 = time.perf_counter()
    panel = _load_panel(settings, tickers)
    timings["data_load"] = time.perf_counter() - t0
    if panel.empty:
        raise ScannerDataError(
            "No stored prices exist for any symbol in the configured universe. "
            "Refresh market data and try again.",
            code="no_universe_prices",
        )

    # ---- validation + matrix build --------------------------------------- #
    t0 = time.perf_counter()
    values = panel["value"].to_numpy(dtype="float64")
    usable = np.isfinite(values) & (values > 0)
    invalid_rows = int((~usable).sum())
    raw_counts = panel.groupby("ticker")["value"].size()
    clean = panel.loc[usable]
    if clean.empty:
        raise ScannerDataError(
            "Every stored price for the configured universe is invalid (null, "
            "zero or non-numeric). Refresh market data and try again.",
            code="invalid_price_data",
        )
    clean_counts = clean.groupby("ticker")["value"].size()
    symbols_with_invalid = int(
        clean_counts.reindex(raw_counts.index).fillna(0).lt(raw_counts).sum()
    )
    close_matrix = clean.pivot(index="date", columns="ticker", values="value").sort_index()
    timings["matrix_build"] = time.perf_counter() - t0

    # ---- indicators (deliberately outside any database lock) -------------- #
    t0 = time.perf_counter()
    benchmark_series = benchmark.set_index("date")["close"]
    indicators = compute_indicators(
        close_matrix, benchmark_series, settings.lookback_days
    )
    timings["indicators"] = time.perf_counter() - t0

    # ---- per-symbol classification ---------------------------------------- #
    t0 = time.perf_counter()
    matrix_tickers = [str(t) for t in close_matrix.columns]
    newest_row = len(close_matrix.index) - 1
    session_counts = {
        ticker: int(count)
        for ticker, count in zip(matrix_tickers, indicators["sessions"])
    }
    staleness = {}
    for position, ticker in enumerate(matrix_tickers):
        last_row = int(indicators["last_pos"][position])
        staleness[ticker] = max(0, newest_row - last_row) if last_row >= 0 else newest_row + 1
    status = classify_symbols(
        tickers,
        raw_counts,
        clean_counts,
        session_counts,
        staleness,
        required_sessions=settings.required_sessions(),
        max_staleness=config.SCANNER_MAX_STALENESS_SESSIONS,
    )

    # ---- criteria over the whole matrix, then restricted to evaluated ----- #
    passes = apply_criteria(indicators, settings)
    evaluated_mask = np.array(
        [not status.is_skipped(ticker) for ticker in matrix_tickers], dtype=bool
    )
    for key in passes:
        passes[key] = np.asarray(passes[key], dtype=bool) & evaluated_mask
    active = settings.active_criteria()
    combined = np.ones(len(matrix_tickers), dtype=bool)
    for key, mask in passes.items():
        if active[key]:
            combined &= mask
    selected = evaluated_mask & combined
    timings["evaluation"] = time.perf_counter() - t0

    # ---- assembly --------------------------------------------------------- #
    t0 = time.perf_counter()
    frame = _result_rows(indicators, passes, selected, matrix_tickers, symbols, names)
    universe_order = {ticker: index for index, ticker in enumerate(tickers)}
    if not frame.empty:
        frame = (
            frame.assign(_order=frame["ticker"].map(universe_order).fillna(1 << 30))
            .sort_values("_order", kind="stable")
            .drop(columns="_order")
            .reset_index(drop=True)
        )
    timings["serialization"] = time.perf_counter() - t0

    # ---- diagnostics ------------------------------------------------------ #
    evaluated = int(evaluated_mask.sum())
    matched = int(selected.sum())
    skipped = sum(status.counts.values())
    if evaluated == 0:
        raise ScannerDataError(
            "None of the symbols in the configured universe could be evaluated: "
            f"{skipped} of {len(tickers)} have no usable, recent price history. "
            "Refresh market data and try again.",
            code="no_evaluable_symbols",
        )

    evaluation_date = pd.Timestamp(close_matrix.index[-1])
    benchmark_last = pd.Timestamp(benchmark["date"].iloc[-1])
    warnings: list[str] = []
    if symbols_with_invalid:
        warnings.append(
            f"{symbols_with_invalid} symbol(s) had non-finite or non-positive "
            f"prices; {invalid_rows:,} row(s) were excluded."
        )
    benchmark_gap = int((close_matrix.index > benchmark_last).sum())
    if benchmark_gap:
        warnings.append(
            f"Benchmark '{settings.benchmark_ticker}' is {benchmark_gap} session(s) "
            "behind the latest stock data; relative strength uses its last known "
            "values."
        )
    if skipped and skipped * 10 >= len(tickers):
        warnings.append(
            f"{skipped} of {len(tickers)} symbols were skipped for missing or "
            "stale data - see the skipped-symbol list."
        )

    active_labels = [CRITERION_LABELS[key] for key, on in active.items() if on]
    if matched:
        explanation = (
            f"{matched} of {evaluated} evaluated symbols passed all "
            f"{len(active_labels)} active criteria."
        )
    else:
        restrictive = min(
            ((key, int(passes[key].sum())) for key, on in active.items() if on),
            key=lambda item: item[1],
        )
        explanation = (
            f"0 of {evaluated} evaluated symbols passed all active criteria "
            f"({', '.join(active_labels)}). The most restrictive filter was "
            f"'{CRITERION_LABELS[restrictive[0]]}' "
            f"({restrictive[1]} of {evaluated} passed)."
            + (f" {skipped} symbol(s) were skipped before evaluation." if skipped else "")
        )

    criterion_counts = {key: int(mask.sum()) for key, mask in passes.items()}
    timings["total"] = time.perf_counter() - started
    diagnostics = {
        "universe_size": len(tickers),
        "symbols_with_data": len(matrix_tickers),
        "symbols_evaluated": evaluated,
        "symbols_matched": matched,
        "symbols_skipped": skipped,
        "skipped": status.counts,
        "skipped_symbols": [
            {
                "ticker": ticker,
                "symbol": symbols.get(ticker, ticker),
                "reason": reason,
            }
            for ticker, reason in status.skipped_examples[
                : config.SCANNER_SKIPPED_SYMBOL_LIMIT
            ]
        ],
        "criterion_pass_counts": criterion_counts,
        "criterion_active": active,
        "benchmark": settings.benchmark_ticker,
        "benchmark_name": _benchmark_name(settings.benchmark_ticker),
        "benchmark_first_date": benchmark["date"].iloc[0].date().isoformat(),
        "benchmark_last_date": benchmark_last.date().isoformat(),
        "benchmark_sessions": int(len(benchmark)),
        "evaluation_date": evaluation_date.date().isoformat(),
        "required_sessions": settings.required_sessions(),
        "lookback_days": settings.lookback_days,
        "price_column": settings.price_column,
        "invalid_price_rows": invalid_rows,
        "symbols_with_invalid_prices": symbols_with_invalid,
        "timings_ms": {key: round(value * 1000.0, 1) for key, value in timings.items()},
        "warnings": warnings,
        "explanation": explanation,
    }
    return ScanOutcome(frame=frame, diagnostics=diagnostics)
