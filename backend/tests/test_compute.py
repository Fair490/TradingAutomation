"""Unit tests for the breadth / advance-decline maths and the universe loader."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402
from backend.compute import breadth as breadth_calc  # noqa: E402
from backend.compute import series as series_utils  # noqa: E402
from backend.loaders import store  # noqa: E402
from backend.loaders.universe import load_universe, to_yahoo_ticker  # noqa: E402


def seed(prices: dict[str, list[tuple[str, float]]]) -> None:
    rows = []
    for ticker, points in prices.items():
        for date, close in points:
            rows.append(
                {"ticker": ticker, "date": date, "close": close, "adj_close": close}
            )
    with store.session() as con:
        store.register_tickers(
            con,
            [
                {"ticker": t, "symbol": t, "name": t, "kind": "stock"}
                for t in prices
            ],
        )
        store.upsert_prices(con, pd.DataFrame(rows))
        store.refresh_ticker_stats(con)


def test_advance_decline_counts(db):
    seed(
        {
            # day2: A up, B down, C unchanged -> 1 adv, 1 dec, 1 unch
            "A": [("2024-01-01", 100), ("2024-01-02", 110)],
            "B": [("2024-01-01", 100), ("2024-01-02", 90)],
            "C": [("2024-01-01", 100), ("2024-01-02", 100)],
        }
    )
    breadth_calc.recompute(full=True)
    with store.session(read_only=True) as con:
        ad = breadth_calc.read_advance_decline(con)
    assert len(ad) == 1
    row = ad.iloc[0]
    assert (row["advances"], row["declines"], row["unchanged"]) == (1, 1, 1)
    assert row["ad_ratio"] == pytest.approx(1.0)
    assert row["ad_line"] == pytest.approx(0.0)


def test_ad_line_is_cumulative(db):
    seed(
        {
            "A": [("2024-01-01", 100), ("2024-01-02", 110), ("2024-01-03", 120)],
            "B": [("2024-01-01", 100), ("2024-01-02", 90), ("2024-01-03", 95)],
            "C": [("2024-01-01", 100), ("2024-01-02", 105), ("2024-01-03", 100)],
        }
    )
    breadth_calc.recompute(full=True)
    with store.session(read_only=True) as con:
        ad = breadth_calc.read_advance_decline(con)
    # day2: 2 adv 1 dec -> +1 ; day3: 2 adv 1 dec -> +1 -> cumulative 2
    assert list(ad["ad_diff"]) == [1, 1]
    assert list(ad["ad_line"]) == [1, 2]


def test_incremental_ad_only_adds_new_days(db):
    seed({"A": [("2024-01-01", 100), ("2024-01-02", 110)]})
    first = breadth_calc.recompute(full=True)
    assert first["advance_decline"] == 1
    # add one more day and recompute incrementally
    seed({"A": [("2024-01-03", 120)]})
    second = breadth_calc.recompute(full=False)
    assert second["advance_decline"] == 1  # only the new day
    with store.session(read_only=True) as con:
        ad = breadth_calc.read_advance_decline(con)
    assert len(ad) == 2
    assert list(ad["ad_line"]) == [1, 2]  # continues from the stored value


def test_breadth_needs_full_window(db, monkeypatch):
    # Save original value
    original_ma_window = config.MA_WINDOW

    monkeypatch.setattr(config, "MA_WINDOW", 5)
    # rebuild the SQL with the patched window
    import importlib

    importlib.reload(breadth_calc)

    dates = pd.bdate_range("2024-01-01", periods=8).date
    seed(
        {
            "UP": [(str(d), 100 + i * 5) for i, d in enumerate(dates)],  # rising
            "DOWN": [(str(d), 100 - i * 5) for i, d in enumerate(dates)],  # falling
            "NEW": [(str(d), 100) for d in dates[-3:]],  # too short for the MA
        }
    )
    breadth_calc.recompute(full=True)
    with store.session(read_only=True) as con:
        br = breadth_calc.read_breadth(con)

    # The first valid date is the 5th observation; NEW never qualifies.
    assert pd.Timestamp(br["date"].min()) == pd.Timestamp(dates[4])
    assert set(br["n_valid"]) == {2}
    assert set(br["n_above"]) == {1}
    assert set(br["pct_above"]) == {50.0}
    assert set(br["above_below"]) == {1.0}

    # Restore config value BEFORE reloading to ensure SQL is rebuilt correctly
    monkeypatch.setattr(config, "MA_WINDOW", original_ma_window)
    importlib.reload(breadth_calc)  # restore the module for other tests


def test_normalise_rebases_to_100():
    frame = pd.DataFrame(
        {"A": [50.0, 75.0, 100.0], "B": [10.0, 5.0, 20.0]},
        index=pd.bdate_range("2024-01-01", periods=3),
    )
    out = series_utils.normalise(frame)
    assert list(out["A"]) == [100.0, 150.0, 200.0]
    assert list(out["B"]) == [100.0, 50.0, 200.0]


def test_range_start():
    today = dt.date(2025, 1, 31)
    assert series_utils.range_start("1M", today) == dt.date(2025, 1, 1)
    assert series_utils.range_start("5Y", today).year == 2020


def test_ticker_mapping():
    assert to_yahoo_ticker("RELIANCE") == "RELIANCE.NS"
    assert to_yahoo_ticker(" tcs ") == "TCS.NS"
    assert to_yahoo_ticker("INFY.NS") == "INFY.NS"


def test_real_universe_file_loads():
    constituents = load_universe(config.UNIVERSE_FILE)
    assert len(constituents) > 500
    assert all(c.ticker.endswith(".NS") for c in constituents)
    symbols = {c.symbol for c in constituents}
    assert "RELIANCE" in symbols


def test_universe_override_column(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text(
        "Company Name,Symbol,Series,Yahoo Ticker\n"
        "Example One,EXONE,EQ,\n"
        "Example Two,EXTWO,EQ,EXTWO.BO\n"
        "Rights Thing,RIGHTS,RR,\n"
    )
    out = load_universe(path)
    tickers = [c.ticker for c in out]
    assert tickers == ["EXONE.NS", "EXTWO.BO", "RIGHTS.NS"]
