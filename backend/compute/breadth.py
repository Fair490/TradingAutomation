"""
Breadth and advance/decline calculations.

Both are done inside DuckDB with window functions - one SQL pass over ~1M
price rows takes well under a second, and the results are stored so the UI
never recalculates on page load.

Incremental by default: only dates after the last stored result are added
(the window functions still read the earlier rows, which is what the 200DMA
needs).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from backend import config
from backend.loaders import store

# Per-stock daily facts: previous close and the 200-day simple moving average.
_PER_STOCK_SQL = f"""
WITH stock_prices AS (
    SELECT p.ticker, p.date, p.close
    FROM prices p
    JOIN tickers t ON t.ticker = p.ticker
    WHERE t.kind = 'stock' AND p.close IS NOT NULL
),
enriched AS (
    SELECT
        ticker,
        date,
        close,
        lag(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
        avg(close) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN {config.MA_WINDOW - 1} PRECEDING AND CURRENT ROW
        ) AS ma,
        count(close) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN {config.MA_WINDOW - 1} PRECEDING AND CURRENT ROW
        ) AS ma_obs
    FROM stock_prices
)
"""


def compute_advance_decline(con, since: dt.date | None = None) -> int:
    """
    Advance = close > previous close, Decline = close < previous close,
    unchanged ignored.  A/D line is the running total of (adv - dec).
    """
    last = con.execute("SELECT max(date), max(ad_line) FROM advance_decline").fetchone()
    last_date = last[0] if last else None
    base_line = con.execute(
        "SELECT ad_line FROM advance_decline WHERE date = ?", [last_date]
    ).fetchone() if last_date else None
    running = float(base_line[0]) if base_line and base_line[0] is not None else 0.0

    start = since or last_date

    daily = con.execute(
        _PER_STOCK_SQL
        + """
        SELECT
            date,
            sum(CASE WHEN close > prev_close THEN 1 ELSE 0 END)  AS advances,
            sum(CASE WHEN close < prev_close THEN 1 ELSE 0 END)  AS declines,
            sum(CASE WHEN close = prev_close THEN 1 ELSE 0 END)  AS unchanged
        FROM enriched
        WHERE prev_close IS NOT NULL
        GROUP BY date
        ORDER BY date
        """
    ).df()

    if daily.empty:
        return 0

    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    if start is not None:
        daily = daily[daily["date"] > start]
    if daily.empty:
        return 0

    daily["ad_diff"] = daily["advances"] - daily["declines"]
    daily["ad_ratio"] = daily.apply(
        lambda r: (r["advances"] / r["declines"]) if r["declines"] else None, axis=1
    )
    daily["ad_line"] = daily["ad_diff"].cumsum() + running

    con.register("incoming_ad", daily)
    con.execute(
        """
        INSERT INTO advance_decline
            (date, advances, declines, unchanged, ad_ratio, ad_diff, ad_line)
        SELECT date, advances, declines, unchanged, ad_ratio, ad_diff, ad_line
        FROM incoming_ad
        ON CONFLICT (date) DO UPDATE SET
            advances = excluded.advances, declines = excluded.declines,
            unchanged = excluded.unchanged, ad_ratio = excluded.ad_ratio,
            ad_diff = excluded.ad_diff, ad_line = excluded.ad_line
        """
    )
    con.unregister("incoming_ad")
    return len(daily)


def compute_breadth(con, since: dt.date | None = None) -> int:
    """
    % of stocks above their 200DMA.  The denominator is the number of stocks
    that have a *valid* 200DMA on that date, so recent listings simply do not
    count until they have enough history.
    """
    last_date = con.execute("SELECT max(date) FROM breadth_200dma").fetchone()[0]
    start = since or last_date

    daily = con.execute(
        _PER_STOCK_SQL
        + f"""
        SELECT
            date,
            count(*)                                            AS n_valid,
            sum(CASE WHEN close > ma THEN 1 ELSE 0 END)         AS n_above,
            sum(CASE WHEN close < ma THEN 1 ELSE 0 END)         AS n_below
        FROM enriched
        WHERE ma_obs >= {config.MA_WINDOW}
        GROUP BY date
        ORDER BY date
        """
    ).df()

    if daily.empty:
        return 0

    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    if start is not None:
        daily = daily[daily["date"] > start]
    if daily.empty:
        return 0

    daily["pct_above"] = 100.0 * daily["n_above"] / daily["n_valid"].replace(0, pd.NA)
    daily["above_below"] = daily["n_above"] / daily["n_below"].replace(0, pd.NA)

    con.register("incoming_breadth", daily)
    con.execute(
        """
        INSERT INTO breadth_200dma
            (date, n_valid, n_above, n_below, pct_above, above_below)
        SELECT date, n_valid, n_above, n_below, pct_above, above_below
        FROM incoming_breadth
        ON CONFLICT (date) DO UPDATE SET
            n_valid = excluded.n_valid, n_above = excluded.n_above,
            n_below = excluded.n_below, pct_above = excluded.pct_above,
            above_below = excluded.above_below
        """
    )
    con.unregister("incoming_breadth")
    return len(daily)


def recompute(full: bool = False) -> dict[str, int]:
    """Update both derived tables.  ``full=True`` rebuilds them from scratch."""
    with store.session() as con:
        if full:
            con.execute("DELETE FROM advance_decline")
            con.execute("DELETE FROM breadth_200dma")
            # Clear the earliest_price_change metadata
            store.set_meta(con, "earliest_price_change", "")
            added_ad = compute_advance_decline(con)
            added_breadth = compute_breadth(con)
        else:
            # Check if we need to recalculate from an earlier date due to price changes
            earliest_change_str = store.get_meta(con, "earliest_price_change", "")
            if earliest_change_str:
                earliest_change = dt.date.fromisoformat(earliest_change_str)
                # Delete data from the earliest change date forward
                con.execute(
                    "DELETE FROM advance_decline WHERE date >= ?",
                    [earliest_change],
                )
                con.execute(
                    "DELETE FROM breadth_200dma WHERE date >= ?",
                    [earliest_change],
                )
                # Clear the metadata
                store.set_meta(con, "earliest_price_change", "")
            
            added_ad = compute_advance_decline(con)
            added_breadth = compute_breadth(con)
        
        store.set_meta(
            con, "last_computed", dt.datetime.now().isoformat(timespec="seconds")
        )
    return {"advance_decline": added_ad, "breadth": added_breadth}


# --------------------------------------------------------------------------- #
# Readers used by the UI
# --------------------------------------------------------------------------- #
def read_advance_decline(con, start: dt.date | None = None) -> pd.DataFrame:
    sql = "SELECT * FROM advance_decline"
    params: list = []
    if start:
        sql += " WHERE date >= ?"
        params.append(start)
    frame = con.execute(sql + " ORDER BY date", params).df()
    if not frame.empty:
        frame["ad_ratio_smooth"] = (
            frame["ad_ratio"].rolling(config.AD_SMOOTHING_WINDOW, min_periods=1).mean()
        )
    return frame


def read_breadth(con, start: dt.date | None = None) -> pd.DataFrame:
    sql = "SELECT * FROM breadth_200dma"
    params: list = []
    if start:
        sql += " WHERE date >= ?"
        params.append(start)
    return con.execute(sql + " ORDER BY date", params).df()
