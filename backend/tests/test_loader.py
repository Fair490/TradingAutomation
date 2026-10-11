"""
Tests for the download plumbing that do not touch the network.

``_tidy`` is the piece that converts whatever shape yfinance hands back into
tidy (ticker, date, close, adj_close) rows, so it is worth pinning down.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402
from backend.loaders import prices as price_loader  # noqa: E402
from backend.loaders import store  # noqa: E402

DATES = pd.to_datetime(["2024-01-01", "2024-01-02"])


def multi_frame(tickers: list[str]) -> pd.DataFrame:
    """Mimic yf.download(..., group_by='ticker') for several tickers."""
    columns = pd.MultiIndex.from_product([tickers, ["Open", "Close", "Adj Close"]])
    data = {}
    for i, ticker in enumerate(tickers):
        data[(ticker, "Open")] = [10.0 + i, 11.0 + i]
        data[(ticker, "Close")] = [12.0 + i, 13.0 + i]
        data[(ticker, "Adj Close")] = [11.5 + i, 12.5 + i]
    return pd.DataFrame(data, index=DATES, columns=columns)


def test_tidy_multi_ticker():
    out = price_loader._tidy(multi_frame(["A.NS", "B.NS"]), ["A.NS", "B.NS"])
    assert set(out["ticker"]) == {"A.NS", "B.NS"}
    assert len(out) == 4
    row = out[(out["ticker"] == "B.NS") & (out["date"] == dt.date(2024, 1, 2))]
    assert row["close"].item() == pytest.approx(14.0)
    assert row["adj_close"].item() == pytest.approx(13.5)


def test_tidy_single_ticker_flat_columns():
    flat = pd.DataFrame(
        {"Open": [1.0, 2.0], "Close": [3.0, 4.0], "Adj Close": [2.9, 3.9]},
        index=DATES,
    )
    out = price_loader._tidy(flat, ["^DJI"])
    assert list(out["ticker"]) == ["^DJI", "^DJI"]
    assert list(out["close"]) == [3.0, 4.0]


def test_tidy_without_adj_close_falls_back_to_close():
    flat = pd.DataFrame({"Close": [5.0, 6.0]}, index=DATES)
    out = price_loader._tidy(flat, ["GC=F"])
    assert list(out["adj_close"]) == [5.0, 6.0]


def test_tidy_handles_empty():
    out = price_loader._tidy(pd.DataFrame(), ["A.NS"])
    assert out.empty
    assert list(out.columns) == ["ticker", "date", "close", "adj_close"]


def test_catalogue_covers_every_configured_series():
    from backend.loaders.universe import Constituent

    rows = price_loader.catalogue(
        [Constituent(symbol="X", ticker="X.NS", name="X Ltd")]
    )
    kinds = pd.Series([r["kind"] for r in rows]).value_counts().to_dict()
    assert kinds["stock"] == 1
    assert kinds["global"] == len(config.GLOBAL_INDICES)
    assert kinds["macro"] == len(config.MACRO_SERIES)
    assert kinds["commodity"] == len(config.COMMODITIES)


def test_upsert_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.duckdb")
    frame = pd.DataFrame(
        {
            "ticker": ["A.NS", "A.NS"],
            "date": ["2024-01-01", "2024-01-02"],
            "close": [10.0, 11.0],
            "adj_close": [10.0, 11.0],
        }
    )
    with store.session() as con:
        store.upsert_prices(con, frame)
        store.upsert_prices(con, frame)  # same rows again
        n = con.execute("SELECT count(*) FROM prices").fetchone()[0]
        assert n == 2
        # a corrected last bar overwrites rather than duplicating
        fixed = frame.tail(1).copy()
        fixed["close"] = 12.0
        store.upsert_prices(con, fixed)
        value = con.execute(
            "SELECT close FROM prices WHERE date = '2024-01-02'"
        ).fetchone()[0]
        assert value == pytest.approx(12.0)
        assert con.execute("SELECT count(*) FROM prices").fetchone()[0] == 2


def test_refresh_only_requests_missing_days(tmp_path, monkeypatch):
    """A second refresh must start from each ticker's last stored date."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.duckdb")

    universe_file = tmp_path / "universe.csv"
    universe_file.write_text("Company Name,Symbol,Series\nAlpha,ALPHA,EQ\n")
    monkeypatch.setattr(config, "UNIVERSE_FILE", universe_file)

    today = dt.date(2024, 6, 10)
    requested: list[tuple[tuple[str, ...], dt.date]] = []

    def fake_download(tickers, start, end=None):
        requested.append((tuple(tickers), start))
        rows = []
        for ticker in tickers:
            for offset in range(3):
                rows.append(
                    {
                        "ticker": ticker,
                        "date": today - dt.timedelta(days=offset),
                        "close": 100.0 + offset,
                        "adj_close": 100.0 + offset,
                    }
                )
        return pd.DataFrame(rows), ""

    monkeypatch.setattr(price_loader, "download_batch", fake_download)
    monkeypatch.setattr(config, "REQUEST_PAUSE_SECONDS", 0)

    first = price_loader.refresh(progress=None, today=today)
    assert first.rows_added > 0
    first_starts = {start for _, start in requested}
    assert min(first_starts) < today - dt.timedelta(days=365 * 5)  # full history

    # Running again on the same day asks for nothing at all.
    requested.clear()
    same_day = price_loader.refresh(progress=None, today=today)
    assert requested == []
    assert same_day.rows_added == 0

    # A few days later every request starts at the stored last date,
    # not five years back.
    later = today + dt.timedelta(days=3)
    requested.clear()
    second = price_loader.refresh(progress=None, today=later)
    assert requested
    assert all(start == today for _, start in requested)
    assert second.new_last_date == today
