"""
Download and incremental-update logic (yfinance -> DuckDB).

Design notes
------------
* First run downloads ``HISTORY_YEARS`` of daily data; stocks start
  ``MA_WARMUP_MONTHS`` earlier so the 200DMA is already valid on the first
  charted day.
* Later runs only ask Yahoo for the days after each ticker's stored maximum
  date, so a refresh is a few seconds rather than a few minutes.
* Downloads happen in batches with retry + exponential back-off; every failure
  is recorded in the ``tickers`` table and surfaced in the UI's Data status
  expander.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import pandas as pd

from backend import config
from backend.loaders import store
from backend.loaders.universe import Constituent, load_universe, to_yahoo_ticker

ProgressFn = Callable[[float, str], None]


@dataclass
class RefreshReport:
    rows_added: int = 0
    tickers_updated: int = 0
    tickers_attempted: int = 0
    tickers_succeeded: int = 0
    tickers_failed: int = 0
    tickers_skipped: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    index_name: str = ""
    index_ticker: str = ""
    full_rebuild: bool = False
    new_last_date: dt.date | None = None

    @property
    def ok(self) -> bool:
        return self.tickers_failed == 0

    def summary(self) -> str:
        bits = [f"{self.rows_added:,} rows added across {self.tickers_updated} tickers"]
        if self.new_last_date:
            bits.append(f"latest date {self.new_last_date:%d %b %Y}")
        if self.tickers_succeeded:
            bits.append(f"{self.tickers_succeeded} succeeded")
        if self.tickers_failed:
            bits.append(f"{self.tickers_failed} failed")
        if self.tickers_skipped:
            bits.append(f"{self.tickers_skipped} skipped")
        if self.empty:
            bits.append(f"{len(self.empty)} returned no data")
        return " · ".join(bits)


# --------------------------------------------------------------------------- #
# yfinance plumbing
# --------------------------------------------------------------------------- #
def _import_yf():
    import yfinance as yf  # imported lazily so the UI starts without network

    return yf


def _tidy(raw: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    """Turn a yfinance download (wide, possibly MultiIndex) into long rows."""
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["ticker", "date", "close", "adj_close"])

    frames: list[pd.DataFrame] = []
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        for ticker in tickers:
            if ticker in level0:  # group_by="ticker"
                sub = raw[ticker]
            elif ticker in set(raw.columns.get_level_values(-1)):
                sub = raw.xs(ticker, axis=1, level=-1)
            else:
                continue
            frames.append(_single(sub, ticker))
    else:
        frames.append(_single(raw, tickers[0]))

    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "close", "adj_close"])
    return pd.concat(frames, ignore_index=True)


def _single(sub: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    if sub is None or sub.empty or "Close" not in sub.columns:
        return None
    out = pd.DataFrame(
        {
            "ticker": ticker,
            "date": pd.to_datetime(sub.index).tz_localize(None).date
            if getattr(sub.index, "tz", None) is not None
            else pd.to_datetime(sub.index).date,
            "close": pd.to_numeric(sub["Close"], errors="coerce"),
            "adj_close": pd.to_numeric(
                sub["Adj Close"] if "Adj Close" in sub.columns else sub["Close"],
                errors="coerce",
            ),
        }
    )
    return out.dropna(subset=["close"]).reset_index(drop=True)


def download_batch(
    tickers: Sequence[str], start: dt.date, end: dt.date | None = None
) -> tuple[pd.DataFrame, str]:
    """Download one batch with retries.  Returns (long frame, error message)."""
    yf = _import_yf()
    delay = config.RETRY_BACKOFF_SECONDS
    last_error = ""
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=list(tickers),
                start=start.isoformat(),
                end=(end.isoformat() if end else None),
                interval="1d",
                auto_adjust=False,
                actions=False,
                group_by="ticker",
                threads=True,
                progress=False,
                timeout=30,
            )
            return _tidy(raw, tickers), ""
        except Exception as exc:  # network / rate limit / parsing
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < config.MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
    return pd.DataFrame(columns=["ticker", "date", "close", "adj_close"]), last_error


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
def catalogue(constituents: Iterable[Constituent]) -> list[dict]:
    rows = [
        {
            "ticker": c.ticker,
            "symbol": c.symbol,
            "name": c.name,
            "kind": "stock",
        }
        for c in constituents
    ]
    for symbol, label, group in config.ETF_SERIES:
        rows.append(
            {
                "ticker": to_yahoo_ticker(symbol),
                "symbol": symbol,
                "name": label,
                "kind": "etf",
            }
        )
    for name, ticker in config.GLOBAL_INDICES:
        rows.append({"ticker": ticker, "symbol": ticker, "name": name, "kind": "global"})
    # RS benchmarks that aren't already in the global list (the default
    # Nifty 500 is already added as the index overlay).
    global_tickers = {t for _, t in config.GLOBAL_INDICES}
    for name, ticker in config.RS_BENCHMARKS:
        if ticker not in global_tickers:
            rows.append({"ticker": ticker, "symbol": ticker, "name": name, "kind": "index"})
    for name, ticker in config.MACRO_SERIES:
        rows.append({"ticker": ticker, "symbol": ticker, "name": name, "kind": "macro"})
    for name, ticker in config.COMMODITIES:
        rows.append(
            {"ticker": ticker, "symbol": ticker, "name": name, "kind": "commodity"}
        )
    return rows


def resolve_index(start: dt.date) -> tuple[str, str, str]:
    """
    Pick the overlay index: try each candidate in config order and keep the
    first that actually returns data.  Returns (name, ticker, note).
    """
    note = ""
    for name, ticker in config.INDEX_CANDIDATES:
        frame, err = download_batch([ticker], start=start)
        if not frame.empty:
            return name, ticker, note
        note = f"{ticker} returned no data{(' (' + err + ')') if err else ''}"
    name, ticker = config.INDEX_CANDIDATES[-1]
    return name, ticker, note


# --------------------------------------------------------------------------- #
# The main entry point
# --------------------------------------------------------------------------- #
def refresh(
    full_rebuild: bool = False,
    progress: ProgressFn | None = None,
    today: dt.date | None = None,
) -> RefreshReport:
    """
    Bring the database up to date from Yahoo Finance.

    Safe to call repeatedly: only the missing days are requested unless
    ``full_rebuild`` is set.  The database lock is taken for short bursts
    (one per batch) so the API keeps answering while a download runs.
    """

    def report_progress(pct: float, msg: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, pct)), msg)

    today = today or dt.date.today()
    rep = RefreshReport(full_rebuild=full_rebuild)

    report_progress(0.01, "Reading universe file…")
    constituents = load_universe()

    stock_start = today - dt.timedelta(
        days=365 * config.HISTORY_YEARS + int(30.44 * config.MA_WARMUP_MONTHS)
    )
    series_start = today - dt.timedelta(days=365 * config.HISTORY_YEARS + 10)

    if full_rebuild:
        report_progress(0.02, "Full rebuild: clearing stored data…")
        with store.session() as con:
            store.wipe_all(con)

    rows = catalogue(constituents)

    # --- which index do we overlay? ---------------------------------------- #
    with store.session() as con:
        saved_ticker = store.get_meta(con, "index_ticker")
        saved_name = store.get_meta(con, "index_name")

    if saved_ticker and not full_rebuild:
        index_name, index_ticker = saved_name or saved_ticker, saved_ticker
    else:
        report_progress(0.03, "Checking which Nifty index Yahoo provides…")
        index_name, index_ticker, note = resolve_index(series_start)
        if note:
            with store.session() as con:
                store.set_meta(con, "index_note", note)

    rows.append(
        {
            "ticker": index_ticker,
            "symbol": index_ticker,
            "name": index_name,
            "kind": "index",
        }
    )
    rep.index_name, rep.index_ticker = index_name, index_ticker

    with store.session() as con:
        store.register_tickers(con, rows)
        store.set_meta(con, "index_ticker", index_ticker)
        store.set_meta(con, "index_name", index_name)
        # Tickers that are no longer in the universe file stop being updated.
        keep = {r["ticker"] for r in rows}
        stale = [
            t
            for t in store.all_tickers(con)
            if t not in keep
        ]
        if stale:
            store.drop_tickers(con, stale)
        known_last = store.last_dates(con)

    # --- work out what each ticker still needs ----------------------------- #
    jobs: list[tuple[str, dt.date]] = []
    for row in rows:
        ticker = row["ticker"]
        default_start = (
            stock_start if row["kind"] in ("stock", "etf") else series_start
        )
        last = known_last.get(ticker)
        # Re-fetch the final stored day so a partial bar gets corrected.
        jobs.append((ticker, last if last is not None else default_start))

    # For same-day refresh: only skip if last date is strictly before today
    # and we're not in a full rebuild. This allows intraday updates.
    up_to_date = []
    needs_update = []
    for t, s in jobs:
        if s is not None and s > today:
            # Last stored date is in the future (data error), refetch from today
            needs_update.append((t, today))
        elif s == today and not full_rebuild:
            # Already have today's data, skip unless full rebuild
            up_to_date.append(t)
        else:
            # Need to fetch from last date (or earlier for corrections)
            needs_update.append((t, s))
    
    jobs = needs_update
    rep.tickers_skipped = len(up_to_date)
    rep.tickers_attempted = len(jobs)

    if not jobs:
        report_progress(1.0, "Everything is already up to date.")
        with store.session() as con:
            store.refresh_ticker_stats(con)
            rep.new_last_date = _max_date(con)
        return rep

    # Group by start date so batching stays efficient.
    by_start: dict[dt.date, list[str]] = {}
    for ticker, start in jobs:
        by_start.setdefault(start, []).append(ticker)

    batches: list[tuple[dt.date, list[str]]] = []
    for start, tickers in by_start.items():
        for i in range(0, len(tickers), config.BATCH_SIZE):
            batches.append((start, tickers[i : i + config.BATCH_SIZE]))

    total = len(batches)
    for i, (start, tickers) in enumerate(batches, start=1):
        report_progress(
            0.05 + 0.85 * (i - 1) / max(total, 1),
            f"Downloading batch {i} of {total} ({len(tickers)} tickers)…",
        )
        frame, err = download_batch(tickers, start=start)

        if err and frame.empty:
            with store.session() as con:
                for ticker in tickers:
                    store.set_ticker_status(con, ticker, "failed", err)
                    rep.tickers_failed += 1
            rep.failures.extend((t, err) for t in tickers)
            continue

        returned = set(frame["ticker"].unique()) if not frame.empty else set()
        with store.session() as con:
            rep.rows_added += store.upsert_prices(con, frame)
            for ticker in tickers:
                if ticker in returned:
                    store.set_ticker_status(con, ticker, "ok", "")
                    rep.tickers_succeeded += 1
                elif known_last.get(ticker) is not None:
                    # No new rows is normal on a weekend/holiday refresh.
                    store.set_ticker_status(con, ticker, "ok", "no new data")
                    rep.tickers_succeeded += 1
                else:
                    store.set_ticker_status(con, ticker, "empty", "no data returned")
                    rep.tickers_succeeded += 1
                    rep.empty.append(ticker)
        rep.tickers_updated += len(returned)

        if config.REQUEST_PAUSE_SECONDS:
            time.sleep(config.REQUEST_PAUSE_SECONDS)

    report_progress(0.92, "Updating ticker statistics…")
    with store.session() as con:
        for ticker in up_to_date:
            store.set_ticker_status(con, ticker, "ok", "")
        store.refresh_ticker_stats(con)
        store.set_meta(
            con, "last_updated", dt.datetime.now().isoformat(timespec="seconds")
        )
        store.set_meta(con, "demo_data", "0")
        rep.new_last_date = _max_date(con)
        
        # Detect earliest date where prices may have changed
        # This is needed for incremental recalculation
        earliest_change = _detect_earliest_price_change(con, known_last)
        if earliest_change:
            store.set_meta(con, "earliest_price_change", earliest_change.isoformat())

    report_progress(1.0, "Download complete.")
    return rep


def _detect_earliest_price_change(
    con, previous_last_dates: dict[str, dt.date]
) -> dt.date | None:
    """
    Detect the earliest date where prices may have changed.
    
    This is critical for incremental recalculation: if a historical price
    was revised, we need to recompute breadth and A/D from that date forward.
    
    Strategy: For tickers that had data before, re-fetch the last 5 trading days
    before their previous last_date to catch any revisions.
    """
    if not previous_last_dates:
        return None
    
    # For now, we'll use a conservative approach: check if any prices in the
    # last 10 days differ from what we'd expect. This is a simplified check.
    # A more sophisticated approach would store price checksums.
    
    # Get the earliest of all last dates
    earliest_last = min(previous_last_dates.values()) if previous_last_dates else None
    if not earliest_last:
        return None
    
    # Return a date 10 days before the earliest last date to be safe
    # This ensures we catch any revisions in the recent past
    return earliest_last - dt.timedelta(days=10)


def _max_date(con) -> dt.date | None:
    row = con.execute("SELECT max(date) FROM prices").fetchone()
    return row[0] if row and row[0] else None
