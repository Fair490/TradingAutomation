"""
Offline demo data generator.

Creates a realistic-looking but entirely SYNTHETIC price history for every
ticker in the catalogue so the dashboard can be opened, reviewed and tested
without touching Yahoo Finance (useful on a machine with no internet, in CI,
or while reviewing the layout).

    python scripts/seed_demo_data.py            # fill the database with demo data
    python scripts/seed_demo_data.py --clear    # wipe it again

The app shows a clear warning banner whenever demo data is loaded.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402
from backend.compute import breadth as breadth_calc  # noqa: E402
from backend.loaders import prices as price_loader  # noqa: E402
from backend.loaders import store  # noqa: E402
from backend.loaders.universe import load_universe  # noqa: E402

RNG = np.random.default_rng(20251009)


def trading_days(start: dt.date, end: dt.date) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)


def gbm(n: int, start_price: float, drift: float, vol: float,
        market: np.ndarray | None = None, beta: float = 0.0) -> np.ndarray:
    shocks = RNG.normal(drift, vol, n)
    if market is not None:
        shocks = shocks * (1 - beta) + beta * market
    return start_price * np.exp(np.cumsum(shocks))


def main(clear: bool) -> None:
    if clear:
        with store.session() as con:
            store.wipe_all(con)
        print("Database cleared.")
        return

    today = dt.date.today()
    stock_start = today - dt.timedelta(
        days=365 * config.HISTORY_YEARS + int(30.44 * config.MA_WARMUP_MONTHS)
    )
    series_start = today - dt.timedelta(days=365 * config.HISTORY_YEARS + 10)

    constituents = load_universe()
    rows = price_loader.catalogue(constituents)
    index_name, index_ticker = config.INDEX_CANDIDATES[-1]  # Nifty 500 fallback
    rows.append({"ticker": index_ticker, "symbol": index_ticker,
                 "name": index_name, "kind": "index"})

    days = trading_days(stock_start, today)
    # One shared "market factor" so breadth swings look like real cycles.
    market = RNG.normal(0.00012, 0.0085, len(days))
    market += 0.0013 * np.sin(np.linspace(0, 7 * np.pi, len(days)))

    with store.session() as con:
        store.register_tickers(con, rows)
        frames: list[pd.DataFrame] = []

        for i, row in enumerate(rows):
            ticker, kind = row["ticker"], row["kind"]
            if kind == "stock":
                idx = days
                mkt = market
                # Recent listings: a slice of stocks start late.
                if i % 37 == 0:
                    cut = RNG.integers(200, 900)
                    idx, mkt = days[cut:], market[cut:]
                price = gbm(len(idx), float(RNG.uniform(60, 3000)),
                            drift=0.0001, vol=0.015, market=mkt,
                            beta=float(RNG.uniform(0.35, 0.8)))
            else:
                idx = days[days >= pd.Timestamp(series_start)]
                mkt = market[-len(idx):]
                if ticker == "^INDIAVIX":
                    # India VIX mean-reverts around ~15 with bounded moves
                    base = 15.0
                    price = base + 4.0 * np.sin(
                        np.linspace(0, 10 * np.pi, len(idx))
                    ) + RNG.normal(0, 1.2, len(idx)).cumsum() * 0.3
                    price = np.clip(price, 8.0, 30.0)
                elif ticker == "^GSPC":
                    base = 5200.0
                    price = gbm(
                        len(idx), base, drift=0.0003, vol=0.009,
                        market=mkt, beta=0.4,
                    )
                else:
                    base = {
                        "index": 18000.0, "global": 25000.0,
                        "macro": 85.0, "commodity": 2000.0, "etf": 250.0,
                    }[kind]
                    if kind == "etf":
                        # a few ETFs are recent listings - mimic a short history
                        if i % 5 == 0:
                            cut = int(len(idx) * 0.6)
                            idx, mkt = idx[cut:], mkt[cut:]
                        price = gbm(
                            len(idx), float(RNG.uniform(60, 700)), drift=0.00016,
                            vol=0.011, market=mkt, beta=float(RNG.uniform(0.5, 0.9)),
                        )
                    else:
                        price = gbm(len(idx), base, drift=0.00012, vol=0.007,
                                    market=mkt, beta=0.4 if kind == "index" else 0.1)
            frames.append(
                pd.DataFrame({
                    "ticker": ticker,
                    "date": idx.date,
                    "close": np.round(price, 2),
                    "adj_close": np.round(price, 2),
                })
            )
            if len(frames) >= 100:
                store.upsert_prices(con, pd.concat(frames, ignore_index=True))
                frames.clear()
                print(f"  …{i + 1}/{len(rows)} tickers")

        if frames:
            store.upsert_prices(con, pd.concat(frames, ignore_index=True))

        store.refresh_ticker_stats(con)
        con.execute("UPDATE tickers SET status = 'ok', message = 'demo data'")
        store.set_meta(con, "index_ticker", index_ticker)
        store.set_meta(con, "index_name", index_name)
        store.set_meta(con, "demo_data", "1")
        store.set_meta(con, "last_updated",
                       dt.datetime.now().isoformat(timespec="seconds"))

    print("Computing breadth and advance/decline…")
    result = breadth_calc.recompute(full=True)
    print(f"Done: {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="wipe stored data")
    main(parser.parse_args().clear)
