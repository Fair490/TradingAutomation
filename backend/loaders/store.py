"""
DuckDB storage layer.

One file (``data/market.duckdb``) holds raw prices, per-ticker download status,
the computed breadth / advance-decline tables and a small key-value meta table.
The backtester planned for part 2 can attach to the same database.
"""

from __future__ import annotations

import datetime as dt
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

import duckdb
import pandas as pd

from backend import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prices (
    ticker    VARCHAR NOT NULL,
    date      DATE    NOT NULL,
    close     DOUBLE,
    adj_close DOUBLE,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS tickers (
    ticker     VARCHAR PRIMARY KEY,
    symbol     VARCHAR,          -- NSE symbol for stocks, else same as ticker
    name       VARCHAR,
    kind       VARCHAR,          -- stock | index | global | macro | commodity
    status     VARCHAR,          -- ok | empty | failed | pending
    message    VARCHAR,
    first_date DATE,
    last_date  DATE,
    n_rows     BIGINT,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS advance_decline (
    date      DATE PRIMARY KEY,
    advances  INTEGER,
    declines  INTEGER,
    unchanged INTEGER,
    ad_ratio  DOUBLE,
    ad_diff   INTEGER,
    ad_line   DOUBLE
);

CREATE TABLE IF NOT EXISTS breadth_200dma (
    date         DATE PRIMARY KEY,
    n_valid      INTEGER,
    n_above      INTEGER,
    n_below      INTEGER,
    pct_above    DOUBLE,
    above_below  DOUBLE
);

CREATE TABLE IF NOT EXISTS meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);
"""


_CON: duckdb.DuckDBPyConnection | None = None
_CON_PATH: Path | None = None
_LOCK = threading.RLock()


def ensure_dirs() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    One shared DuckDB connection per process.

    DuckDB allows a single writer process, and opening the same file twice
    inside one process with different settings raises.  The API serves reads
    while a refresh writes, so everything goes through this connection and the
    module-level lock instead.
    """
    global _CON, _CON_PATH
    with _LOCK:
        path = Path(config.DB_PATH)
        if _CON is not None and _CON_PATH == path:
            return _CON
        if _CON is not None:  # the configured path changed (tests)
            try:
                _CON.close()
            except Exception:
                pass
        ensure_dirs()
        _CON = duckdb.connect(str(path))
        _CON.execute(SCHEMA_SQL)
        _CON_PATH = path
        return _CON


def reset_connection() -> None:
    """Close the shared connection (used by tests and on shutdown)."""
    global _CON, _CON_PATH
    with _LOCK:
        if _CON is not None:
            try:
                _CON.close()
            except Exception:
                pass
        _CON, _CON_PATH = None, None


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Backwards-compatible alias; ``read_only`` is accepted but ignored."""
    return get_connection()


@contextmanager
def session(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """
    Serialised access to the shared connection.

    Keep the block short: a long-running download must release the lock
    between batches so API reads stay responsive.
    """
    con = get_connection()
    with _LOCK:
        yield con


# --------------------------------------------------------------------------- #
# meta helpers
# --------------------------------------------------------------------------- #
def set_meta(con: duckdb.DuckDBPyConnection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        [key, str(value)],
    )


def get_meta(con: duckdb.DuckDBPyConnection, key: str, default: str | None = None):
    row = con.execute("SELECT value FROM meta WHERE key = ?", [key]).fetchone()
    return row[0] if row else default


# --------------------------------------------------------------------------- #
# price helpers
# --------------------------------------------------------------------------- #
def upsert_prices(con: duckdb.DuckDBPyConnection, frame: pd.DataFrame) -> int:
    """
    Insert rows of (ticker, date, close, adj_close); existing (ticker, date)
    pairs are overwritten so a partial last day gets corrected on the next run.
    """
    if frame is None or frame.empty:
        return 0
    frame = frame[["ticker", "date", "close", "adj_close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame = frame.dropna(subset=["ticker", "date", "close"])
    frame = frame.drop_duplicates(subset=["ticker", "date"], keep="last")
    if frame.empty:
        return 0
    con.register("incoming_prices", frame)
    con.execute(
        """
        INSERT INTO prices (ticker, date, close, adj_close)
        SELECT ticker, date, close, adj_close FROM incoming_prices
        ON CONFLICT (ticker, date) DO UPDATE
            SET close = excluded.close, adj_close = excluded.adj_close
        """
    )
    con.unregister("incoming_prices")
    return len(frame)


def last_dates(con: duckdb.DuckDBPyConnection) -> dict[str, dt.date]:
    rows = con.execute(
        "SELECT ticker, max(date) FROM prices GROUP BY ticker"
    ).fetchall()
    return {t: d for t, d in rows if d is not None}


def register_tickers(con: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    """Insert/update the ticker catalogue (name, kind, symbol)."""
    if not rows:
        return
    frame = pd.DataFrame(rows)
    con.register("incoming_tickers", frame)
    con.execute(
        """
        INSERT INTO tickers (ticker, symbol, name, kind, status, updated_at)
        SELECT ticker, symbol, name, kind, 'pending', now() FROM incoming_tickers
        ON CONFLICT (ticker) DO UPDATE
            SET symbol = excluded.symbol,
                name   = excluded.name,
                kind   = excluded.kind
        """
    )
    con.unregister("incoming_tickers")


def refresh_ticker_stats(con: duckdb.DuckDBPyConnection) -> None:
    """Recompute first/last date and row counts for every known ticker."""
    con.execute(
        """
        UPDATE tickers AS t
        SET first_date = s.first_date,
            last_date  = s.last_date,
            n_rows     = s.n_rows,
            updated_at = now()
        FROM (
            SELECT ticker, min(date) AS first_date, max(date) AS last_date,
                   count(*) AS n_rows
            FROM prices GROUP BY ticker
        ) AS s
        WHERE t.ticker = s.ticker
        """
    )
    con.execute(
        "UPDATE tickers SET n_rows = 0 WHERE n_rows IS NULL"
    )


def set_ticker_status(
    con: duckdb.DuckDBPyConnection, ticker: str, status: str, message: str = ""
) -> None:
    con.execute(
        "UPDATE tickers SET status = ?, message = ?, updated_at = now() "
        "WHERE ticker = ?",
        [status, message, ticker],
    )


def ticker_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        "SELECT ticker, symbol, name, kind, status, message, first_date, "
        "last_date, n_rows FROM tickers ORDER BY kind, ticker"
    ).df()


def stock_tickers(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            "SELECT ticker FROM tickers WHERE kind = 'stock' ORDER BY ticker"
        ).fetchall()
    ]


def load_series(
    con: duckdb.DuckDBPyConnection, ticker: str, start: dt.date | None = None
) -> pd.DataFrame:
    """Return a date/close/adj_close frame for one ticker."""
    sql = "SELECT date, close, adj_close FROM prices WHERE ticker = ?"
    params: list = [ticker]
    if start is not None:
        sql += " AND date >= ?"
        params.append(start)
    sql += " ORDER BY date"
    return con.execute(sql, params).df()


def count_prices(con: duckdb.DuckDBPyConnection) -> int:
    """Total number of stored price rows (cheap readiness check)."""
    return int(con.execute("SELECT count(*) FROM prices").fetchone()[0])


def known_ticker_rows(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """ticker -> kind for everything in the catalogue (no price reads)."""
    return {
        t: (kind or "")
        for t, kind in con.execute("SELECT ticker, kind FROM tickers").fetchall()
    }


def load_price_panel(
    con: duckdb.DuckDBPyConnection,
    tickers: Sequence[str],
    column: str = "close",
    start: dt.date | None = None,
) -> pd.DataFrame:
    """
    One query for many tickers: long frame with ticker / date / value.

    The scanner needs the same 5-year history for the whole universe; fetching
    it ticker-by-ticker is an N+1 pattern that costs one table scan per symbol.
    This performs a single pass joined against the requested ticker list.
    """
    if column not in ("close", "adj_close"):
        raise ValueError(f"Unsupported price column: {column!r}")
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", "value"])

    wanted = pd.DataFrame({"ticker": list(dict.fromkeys(tickers))})
    con.register("wanted_tickers", wanted)
    try:
        sql = (
            f"SELECT p.ticker, p.date, p.{column} AS value "
            "FROM prices p JOIN wanted_tickers w ON w.ticker = p.ticker"
        )
        params: list = []
        if start is not None:
            sql += " WHERE p.date >= ?"
            params.append(start)
        sql += " ORDER BY p.ticker, p.date"
        return con.execute(sql, params).df()
    finally:
        con.unregister("wanted_tickers")


def wipe_all(con: duckdb.DuckDBPyConnection) -> None:
    """Full rebuild support: drop every stored row but keep the schema."""
    for table in ("prices", "advance_decline", "breadth_200dma", "tickers", "meta"):
        con.execute(f"DELETE FROM {table}")


def all_tickers(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [r[0] for r in con.execute("SELECT ticker FROM tickers").fetchall()]


def drop_tickers(con: duckdb.DuckDBPyConnection, tickers: list[str]) -> None:
    """Forget tickers that are no longer part of the universe file."""
    if not tickers:
        return
    frame = pd.DataFrame({"ticker": tickers})
    con.register("stale_tickers", frame)
    con.execute("DELETE FROM prices WHERE ticker IN (SELECT ticker FROM stale_tickers)")
    con.execute("DELETE FROM tickers WHERE ticker IN (SELECT ticker FROM stale_tickers)")
    con.unregister("stale_tickers")
