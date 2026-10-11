"""End-to-end tests for the HTTP API (no network, temporary database)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402
from backend.compute import breadth as breadth_calc  # noqa: E402
from backend.loaders import store  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.duckdb")
    monkeypatch.setattr(config, "MA_WINDOW", 3)

    import importlib

    importlib.reload(breadth_calc)

    dates = pd.bdate_range("2024-01-01", periods=12).date
    rows = []
    for ticker, slope in (("A.NS", 2.0), ("B.NS", -1.0)):
        for i, date in enumerate(dates):
            price = 100 + slope * i
            rows.append(
                {"ticker": ticker, "date": date, "close": price, "adj_close": price}
            )
    # one ETF with prices; every other configured ETF stays empty on purpose,
    # which is what a first refresh looks like.
    etf_symbol, etf_label, _etf_group = config.ETF_SERIES[0]
    etf_ticker = f"{etf_symbol}.NS"
    for i, date in enumerate(dates):
        rows.append(
            {
                "ticker": etf_ticker,
                "date": date,
                "close": 100 + 3 * i,
                "adj_close": 100 + 3 * i,
            }
        )

    for ticker, kind, name in (
        ("^CRSLDX", "index", "Nifty 500"),
        ("^DJI", "global", "Dow Jones"),
        ("INR=X", "macro", "USD/INR"),
        ("GC=F", "commodity", "Gold"),
    ):
        for i, date in enumerate(dates):
            rows.append(
                {
                    "ticker": ticker,
                    "date": date,
                    "close": 1000 + i,
                    "adj_close": 1000 + i,
                }
            )

    # RS benchmarks need prices too
    for i, date in enumerate(dates):
        rows.append(
            {
                "ticker": "^NSEI",
                "date": date,
                "close": 14000 + 50 * i,
                "adj_close": 14000 + 50 * i,
            }
        )
        rows.append(
            {
                "ticker": "^NSEBANK",
                "date": date,
                "close": 30000 + 100 * i,
                "adj_close": 30000 + 100 * i,
            }
        )

    with store.session() as con:
        store.register_tickers(
            con,
            [
                {"ticker": "A.NS", "symbol": "A", "name": "Alpha", "kind": "stock"},
                {"ticker": "B.NS", "symbol": "B", "name": "Beta", "kind": "stock"},
                {
                    "ticker": "^CRSLDX",
                    "symbol": "^CRSLDX",
                    "name": "Nifty 500",
                    "kind": "index",
                },
                {"ticker": "^DJI", "symbol": "^DJI", "name": "Dow Jones", "kind": "global"},
                {"ticker": "INR=X", "symbol": "INR=X", "name": "USD/INR", "kind": "macro"},
                {"ticker": "GC=F", "symbol": "GC=F", "name": "Gold", "kind": "commodity"},
                {
                    "ticker": etf_ticker,
                    "symbol": etf_symbol,
                    "name": etf_label,
                    "kind": "etf",
                },
                {"ticker": "^NSEI", "symbol": "^NSEI", "name": "Nifty 50", "kind": "index"},
                {"ticker": "^NSEBANK", "symbol": "^NSEBANK", "name": "Bank Nifty", "kind": "index"},
            ],
        )
        store.upsert_prices(con, pd.DataFrame(rows))
        store.refresh_ticker_stats(con)
        con.execute("UPDATE tickers SET status = 'ok', message = ''")
        store.set_meta(con, "index_ticker", "^CRSLDX")
        store.set_meta(con, "index_name", "Nifty 500")
    breadth_calc.recompute(full=True)

    with TestClient(app) as test_client:
        yield test_client

    store.reset_connection()
    importlib.reload(breadth_calc)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_meta(client):
    body = client.get("/api/meta").json()
    assert body["has_data"] is True
    assert body["index_name"] == "Nifty 500"
    assert body["n_stocks"] == 2
    assert body["ranges"] == ["1M", "3M", "6M", "1Y", "3Y", "5Y"]


def test_breadth_shape(client):
    body = client.get("/api/breadth?range=5Y").json()
    assert body["points"], "expected breadth points"
    assert body["index"], "expected the overlay index series"
    assert body["thresholds"] == {"overbought": 80.0, "midline": 50.0, "oversold": 20.0}
    # one stock rising, one falling -> 50% above the moving average
    assert body["latest"]["pct_above"] == pytest.approx(50.0)
    assert body["latest"]["n_above"] == 1
    assert body["latest"]["n_below"] == 1


def test_advance_decline_shape(client):
    body = client.get("/api/advance-decline?range=5Y").json()
    point = body["points"][-1]
    assert point["advances"] == 1
    assert point["declines"] == 1
    assert point["ad_ratio"] == pytest.approx(1.0)
    assert body["smoothing_window"] == 10


def test_global_cards(client):
    body = client.get("/api/global").json()
    names = [c["name"] for c in body]
    assert "Dow Jones" in names
    dow = next(c for c in body if c["ticker"] == "^DJI")
    assert dow["last_close"] is not None
    assert dow["change_pct"] is not None


def test_macro_and_commodities(client):
    macro = client.get("/api/macro?range=5Y").json()["series"]
    assert [s["name"] for s in macro][0] == "USD/INR"
    assert macro[0]["note"], "USD/INR should explain the direction"
    comm = client.get("/api/commodities?range=5Y").json()["series"]
    assert any(s["name"] == "Gold" and s["points"] for s in comm)


def test_bad_range_is_rejected(client):
    res = client.get("/api/breadth?range=10Y")
    assert res.status_code == 400
    assert "Unknown range" in res.json()["detail"]


def test_status_lists_tickers(client):
    body = client.get("/api/status").json()
    assert body["n_ok"] == len(body["tickers"]) == 9
    assert body["n_problem"] == 0


def test_refresh_status_idle(client):
    body = client.get("/api/refresh/status").json()
    assert body["running"] is False


def test_etf_leaderboard(client):
    body = client.get("/api/etfs?range=5Y").json()
    assert len(body["etfs"]) == len(config.ETF_SERIES)
    assert body["benchmark_name"] == "Nifty 500"
    assert body["groups"], "expected at least one ETF group"

    symbol = config.ETF_SERIES[0][0]
    seeded = next(e for e in body["etfs"] if e["symbol"] == symbol)
    assert seeded["ticker"] == f"{symbol}.NS"
    # 100 -> 133 over the window, index 1000 -> 1011, so it beats the benchmark
    assert seeded["change_pct"] == pytest.approx(33.0)
    assert seeded["relative_pct"] > 0
    assert seeded["spark"], "expected sparkline points"
    assert len(seeded["spark"]) <= config.ETF_SPARK_POINTS

    # ETFs without prices still appear, just empty - the UI greys them out
    empty = [e for e in body["etfs"] if e["symbol"] != symbol]
    assert empty and all(e["last_value"] is None and e["spark"] == [] for e in empty)


def test_etf_compare_includes_benchmark(client):
    symbol = config.ETF_SERIES[0][0]
    other = config.ETF_SERIES[1][0]
    body = client.get(f"/api/etfs/compare?symbols={symbol},{other}&range=5Y").json()
    assert [s["symbol"] for s in body["series"]] == [symbol, other]
    assert body["series"][0]["points"], "seeded ETF should have points"
    assert body["series"][1]["points"] == []
    assert body["benchmark"]["name"] == "Nifty 500"
    assert body["benchmark"]["points"]

    without = client.get(
        f"/api/etfs/compare?symbols={symbol}&range=5Y&benchmark=false"
    ).json()
    assert without["benchmark"] is None


def test_etf_compare_rejects_unknown_symbol(client):
    res = client.get("/api/etfs/compare?symbols=NOTANETF&range=5Y")
    assert res.status_code == 400
    assert "Unknown ETF symbol" in res.json()["detail"]


def test_global_card_period_changes_and_units(client):
    body = client.get("/api/global").json()
    assert len(body) == len(config.GLOBAL_INDICES)
    dow = next(c for c in body if c["ticker"] == "^DJI")
    # Every card ships the 1-month / 1-year / 5-year change fields.
    assert "change_1m" in dow and "change_1y" in dow and "change_5y" in dow
    assert "unit" in dow and dow["unit"] == "price"
    assert "stale" in dow


def test_series_endpoint_returns_mas_and_period_changes(client):
    body = client.get("/api/commodities?range=5Y").json()
    gold = next(s for s in body["series"] if s["name"] == "Gold")
    assert gold["unit"] == "USD/oz"
    # Fields exist (may be None when the fixture has too little history)
    assert "change_1m" in gold and "change_1y" in gold and "change_5y" in gold
    assert "moving_averages" in gold
    assert gold["moving_averages"] is None or len(gold["moving_averages"]["ma50"]) == len(gold["points"])


def test_macro_us10y_in_bps(client):
    body = client.get("/api/macro?range=5Y").json()
    ten_y = next(s for s in body["series"] if s["ticker"] == "^TNX")
    assert ten_y["unit"] == "bps"
    # bps values should be roughly in the 100s - 500s range for a yield
    if ten_y["last_value"] is not None:
        assert 50 < abs(ten_y["last_value"]) < 2000


def test_etf_periods_and_stats(client):
    body = client.get("/api/etfs?range=5Y").json()
    seeded = next(e for e in body["etfs"] if e["symbol"] == config.ETF_SERIES[0][0])
    assert set(seeded["periods"]) == set(config.ETF_RANK_PERIODS)
    one_m = seeded["periods"]["1M"]
    assert "change_pct" in one_m and "relative_pct" in one_m
    # 52w / 50dma / 150dma fields exist
    assert "pct_from_52w_high" in seeded
    assert "pct_from_50dma" in seeded
    assert "pct_from_150dma" in seeded


def test_ad_latest_ratios_and_divergence(client):
    body = client.get("/api/advance-decline?range=5Y").json()
    assert "latest_daily_ratio" in body
    assert "latest_avg_ratio" in body
    assert "divergence" in body
    # With one stock rising and one falling daily, ratio should be ~1
    assert body["latest_daily_ratio"] == pytest.approx(1.0)


def test_rs_benchmark_endpoint(client):
    # Default benchmark
    body = client.get("/api/rs-benchmark").json()
    assert body["ticker"] == "^CRSLDX"
    assert body["points"], "expected price points"
    assert body["range"] == "5Y"

    # Explicit Nifty 50
    body = client.get("/api/rs-benchmark?ticker=^NSEI&range=5Y").json()
    assert body["ticker"] == "^NSEI"
    assert body["name"] == "Nifty 50"
    assert body["points"]

    # Bank Nifty
    body = client.get("/api/rs-benchmark?ticker=^NSEBANK&range=5Y").json()
    assert body["ticker"] == "^NSEBANK"

    # Unknown benchmark
    res = client.get("/api/rs-benchmark?ticker=^NOTREAL")
    assert res.status_code == 400


def test_global_chart_endpoint(client):
    body = client.get("/api/global-chart?range=5Y").json()
    # VIX should be excluded (different scale)
    tickers = [s["ticker"] for s in body["series"]]
    assert "^INDIAVIX" not in tickers
    assert "^DJI" in tickers
    assert "^GSPC" in tickers
    # Each series should have MAs and unit
    for s in body["series"]:
        assert s["unit"] == "price"
        assert "moving_averages" in s
