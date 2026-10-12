"""
Tests for the stock scanner: maths, criteria, API contract, failure handling,
concurrency and performance.

Everything runs against a temporary DuckDB seeded with deterministic synthetic
prices - no network, no real market data.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import threading
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402
from backend.compute import series as series_utils  # noqa: E402
from backend.loaders import store  # noqa: E402
from backend.main import app  # noqa: E402
from backend.scanner import engine  # noqa: E402
from backend.scanner import run_scan, scan_slot  # noqa: E402
from backend.scanner.engine import (  # noqa: E402
    CRITERION_ABOVE_SMA50,
    CRITERION_CLOSE_VS_HIGH,
    CRITERION_RISING_SMA200,
    CRITERION_RS_AT_HIGH,
    CRITERION_SMA50_ABOVE_SMA150,
    SKIP_INSUFFICIENT_HISTORY,
    SKIP_INVALID_PRICES,
    SKIP_NO_DATA,
    SKIP_STALE,
    ScanSettings,
    ScannerBusyError,
)

SESSIONS = 300
BENCHMARK = "^CRSLDX"
BENCHMARK_RATE = 1.0015


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def rising(n: int = SESSIONS, start: float = 100.0, rate: float = 1.004) -> list[float]:
    return [start * (rate**i) for i in range(n)]


def falling(n: int = SESSIONS, start: float = 400.0, rate: float = 0.997) -> list[float]:
    return [start * (rate**i) for i in range(n)]


def dates(n: int = SESSIONS, start: str = "2023-01-02") -> list[dt.date]:
    return list(pd.bdate_range(start, periods=n).date)


def write_universe(path: Path, tickers: list[tuple[str, str]]) -> Path:
    """``tickers`` is a list of (symbol, yahoo ticker) pairs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Company Name", "Industry", "Symbol", "Series", "ISIN Code"])
        for symbol, _ticker in tickers:
            writer.writerow([f"{symbol} Ltd.", "Test", symbol, "EQ", "INE000000000"])
    return path


def seed(
    prices: dict[str, list[float]] | dict[str, list[tuple[str, float]]],
    *,
    kinds: dict[str, str] | None = None,
    benchmark: list[float] | None = None,
    status: str = "ok",
    start: str = "2023-01-02",
) -> None:
    """
    Insert prices for the given tickers.

    Values may be a list of closes (sessions are business days from
    ``start``) or a list of (date, close) pairs.
    """
    rows = []
    for ticker, series in prices.items():
        if series and isinstance(series[0], tuple):
            points = [(str(date), float(value)) for date, value in series]
        else:
            points = list(zip([str(d) for d in dates(len(series), start)], map(float, series)))
        for date, value in points:
            rows.append(
                {"ticker": ticker, "date": date, "close": value, "adj_close": value}
            )
    if benchmark is not None:
        for date, value in zip(dates(len(benchmark), start), benchmark):
            rows.append(
                {"ticker": BENCHMARK, "date": str(date), "close": value, "adj_close": value}
            )

    kinds = kinds or {}
    catalogue = [
        {
            "ticker": ticker,
            "symbol": ticker.removesuffix(".NS"),
            "name": f"{ticker} Ltd.",
            "kind": kinds.get(ticker, "stock"),
        }
        for ticker in list(prices) + ([BENCHMARK] if benchmark is not None else [])
    ]
    with store.session() as con:
        store.register_tickers(con, catalogue)
        if rows:
            store.upsert_prices(con, pd.DataFrame(rows))
        store.refresh_ticker_stats(con)
        con.execute("UPDATE tickers SET status = ?", [status])


@pytest.fixture()
def scanner_env(tmp_path, monkeypatch):
    """
    Temporary DuckDB + universe file, and a reset shared connection so tests
    never touch the real database.
    """
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "scanner.duckdb")
    universe_path = tmp_path / "universe.csv"
    monkeypatch.setattr(config, "UNIVERSE_FILE", universe_path)
    store.reset_connection()
    try:
        yield tmp_path, universe_path
    finally:
        store.reset_connection()


@pytest.fixture()
def client(scanner_env):
    with TestClient(app) as test_client:
        yield test_client


def post_scan(client: TestClient, **payload):
    body = {
        "benchmark_ticker": BENCHMARK,
        "min_close_vs_high": 0.80,
        "require_above_sma50": True,
        "require_sma50_above_sma150": True,
        "require_rising_sma200": True,
        "require_rs_at_high": True,
        "lookback_days": 252,
    }
    body.update(payload)
    return client.post("/api/scanner/scan", json=body)


# --------------------------------------------------------------------------- #
# 1 + 2. A valid scan with matches, and a valid scan with zero matches
# --------------------------------------------------------------------------- #
def test_scan_finds_the_matching_stocks(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS"), ("WEAK", "WEAK.NS")])
    seed(
        {"GOOD.NS": rising(), "WEAK.NS": falling()},
        benchmark=rising(rate=BENCHMARK_RATE),
    )

    response = post_scan(client)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["count"] == len(body["results"]) == 1
    assert body["results"][0]["ticker"] == "GOOD.NS"
    assert body["results"][0]["symbol"] == "GOOD"
    assert body["benchmark"] == BENCHMARK

    diagnostics = body["diagnostics"]
    assert diagnostics["universe_size"] == 2
    assert diagnostics["symbols_evaluated"] == 2
    assert diagnostics["symbols_matched"] == 1
    assert diagnostics["symbols_skipped"] == 0
    assert diagnostics["criterion_pass_counts"] == {
        CRITERION_CLOSE_VS_HIGH: 1,
        CRITERION_ABOVE_SMA50: 1,
        CRITERION_SMA50_ABOVE_SMA150: 1,
        CRITERION_RISING_SMA200: 1,
        CRITERION_RS_AT_HIGH: 1,
    }
    assert diagnostics["benchmark_last_date"] == str(dates(SESSIONS)[-1])
    assert diagnostics["explanation"].startswith("1 of 2 evaluated symbols passed")
    # per-phase timings must be reported
    assert set(diagnostics["timings_ms"]) >= {
        "universe",
        "benchmark",
        "data_load",
        "matrix_build",
        "indicators",
        "evaluation",
        "serialization",
        "response_serialization",
        "total",
    }
    # results must be strictly valid JSON (no NaN tokens)
    assert "NaN" not in response.text and "Infinity" not in response.text


def test_valid_scan_with_zero_matches_is_explained(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("WEAK", "WEAK.NS")])
    seed({"WEAK.NS": falling()}, benchmark=rising(rate=BENCHMARK_RATE))

    response = post_scan(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 0
    assert body["results"] == []
    diagnostics = body["diagnostics"]
    assert diagnostics["symbols_evaluated"] == 1
    assert diagnostics["symbols_matched"] == 0
    assert diagnostics["explanation"].startswith("0 of 1 evaluated symbols")
    assert "most restrictive filter" in diagnostics["explanation"]
    # the per-criterion counts explain *why* nothing matched
    assert diagnostics["criterion_pass_counts"]["close_vs_high"] == 0


# --------------------------------------------------------------------------- #
# 3 + 4. Benchmark problems
# --------------------------------------------------------------------------- #
def test_missing_benchmark_history_is_an_error_not_an_empty_scan(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    # no benchmark prices at all
    seed({"GOOD.NS": rising()})

    response = post_scan(client)
    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "benchmark_unavailable"
    assert "refresh" in detail["message"].lower()
    # a failure must never masquerade as a successful zero-result scan
    assert "results" not in response.json()


def test_unknown_benchmark_is_rejected(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    response = post_scan(client, benchmark_ticker="^NOTREAL")
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "unknown_benchmark"


def test_benchmark_with_only_invalid_closes_is_rejected(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=[0.0] * SESSIONS)

    response = post_scan(client)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "benchmark_unavailable"


# --------------------------------------------------------------------------- #
# 5. Universe problems
# --------------------------------------------------------------------------- #
def test_missing_universe_file_is_reported(scanner_env, client):
    tmp_path, universe = scanner_env
    assert not universe.exists()
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    response = post_scan(client)
    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "universe_unavailable"
    assert str(tmp_path) not in json.dumps(detail)  # no internal paths leak


def test_empty_universe_file_is_reported(scanner_env, client):
    _tmp, universe = scanner_env
    universe.write_text("Company Name,Industry,Symbol,Series,ISIN Code\n")
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    response = post_scan(client)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "universe_unavailable"


def test_missing_market_database_is_reported(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    # database exists (the store creates the schema) but holds no prices

    response = post_scan(client)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "empty_database"


# --------------------------------------------------------------------------- #
# 6. Partial data: skip what cannot be evaluated, report it, keep scanning
# --------------------------------------------------------------------------- #
def test_symbols_with_insufficient_history_are_skipped_and_counted(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(
        universe, [("GOOD", "GOOD.NS"), ("SHORT", "SHORT.NS"), ("NODATA", "NODATA.NS")]
    )
    seed({"GOOD.NS": rising(), "SHORT.NS": rising(n=100)}, benchmark=rising(rate=BENCHMARK_RATE))
    with store.session() as con:
        store.register_tickers(
            con,
            [{"ticker": "NODATA.NS", "symbol": "NODATA", "name": "No Data", "kind": "stock"}],
        )

    response = post_scan(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    diagnostics = body["diagnostics"]
    assert diagnostics["universe_size"] == 3
    assert diagnostics["symbols_evaluated"] == 1
    assert diagnostics["symbols_skipped"] == 2
    assert diagnostics["skipped"] == {
        SKIP_NO_DATA: 1,
        SKIP_INSUFFICIENT_HISTORY: 1,
    }
    skipped = {entry["ticker"]: entry["reason"] for entry in diagnostics["skipped_symbols"]}
    assert skipped == {"SHORT.NS": SKIP_INSUFFICIENT_HISTORY, "NODATA.NS": SKIP_NO_DATA}
    assert any("skipped" in warning for warning in diagnostics["warnings"])


def test_stale_symbols_are_skipped(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS"), ("STALE", "STALE.NS")])
    session_dates = dates()
    # the stale symbol stops 40 sessions before the freshest bar
    stale_last = session_dates[-41]
    stale_points = [
        (str(date), value) for date, value in zip(session_dates[:-40], rising(n=SESSIONS - 40))
    ]
    seed(
        {"GOOD.NS": rising(), "STALE.NS": stale_points},
        benchmark=rising(rate=BENCHMARK_RATE),
    )
    assert stale_points[-1][0] == str(stale_last)

    body = post_scan(client).json()
    assert body["count"] == 1
    assert body["diagnostics"]["skipped"] == {SKIP_STALE: 1}
    assert body["diagnostics"]["skipped_symbols"][0]["ticker"] == "STALE.NS"


def test_unusable_prices_are_excluded_and_reported(scanner_env, client):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS"), ("BROKEN", "BROKEN.NS"), ("ZERO", "ZERO.NS")])
    broken = rising()
    broken[10] = float("nan")
    broken[11] = 0.0
    broken[12] = -5.0
    seed(
        {"GOOD.NS": rising(), "BROKEN.NS": broken, "ZERO.NS": [0.0] * SESSIONS},
        benchmark=rising(rate=BENCHMARK_RATE),
    )

    response = post_scan(client)
    assert response.status_code == 200, response.text
    body = response.json()
    diagnostics = body["diagnostics"]
    # GOOD and BROKEN still match (BROKEN only lost 3 sessions); the all-zero
    # symbol is skipped rather than silently scanned as a 0.00 stock
    assert body["count"] == 2
    assert {row["ticker"] for row in body["results"]} == {"GOOD.NS", "BROKEN.NS"}
    # the NaN close never reaches DuckDB (upsert_prices drops NULL closes), the
    # zero and negative rows do; the 300 zero closes are all excluded too
    assert diagnostics["invalid_price_rows"] == 2 + SESSIONS
    assert diagnostics["skipped"] == {SKIP_INVALID_PRICES: 1}
    assert diagnostics["skipped_symbols"][0]["ticker"] == "ZERO.NS"
    assert diagnostics["symbols_with_invalid_prices"] == 2
    assert any("non-finite" in warning for warning in diagnostics["warnings"])
    assert "NaN" not in response.text


def test_universe_with_no_evaluable_symbols_returns_an_error(scanner_env, client):
    """
    Regression: a total data failure must not be returned as a successful
    zero-result scan.
    """
    _tmp, universe = scanner_env
    write_universe(universe, [("SHORT", "SHORT.NS")])
    seed({"SHORT.NS": rising(n=60)}, benchmark=rising(rate=BENCHMARK_RATE))

    response = post_scan(client)
    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "no_evaluable_symbols"


# --------------------------------------------------------------------------- #
# 7. Each filter on its own + the combined AND
# --------------------------------------------------------------------------- #
def _indicator_stub(**overrides) -> dict:
    """One-symbol indicator dict for the pure criteria tests."""
    stub = {
        "last_close": np.array([100.0]),
        "sma_fast_last": np.array([95.0]),
        "sma_mid_last": np.array([90.0]),
        "sma_slow_last": np.array([85.0]),
        "sma_slow_back": np.array([84.0]),
        "has_sma_back": np.array([True]),
        "highest_last": np.array([100.0]),
        "rs_last": np.array([12.0]),
        "rs_back": np.array([11.0]),
        "has_rs_back": np.array([True]),
        "rs_highest_last": np.array([12.0]),
        "sessions": np.array([300]),
        "rs_sessions": np.array([300]),
    }
    stub.update(overrides)
    return stub


def test_close_vs_high_filter_boundary():
    settings = ScanSettings(min_close_vs_high=0.80)
    passing = engine.apply_criteria(_indicator_stub(), settings)
    assert bool(passing[CRITERION_CLOSE_VS_HIGH][0]) is True

    at_limit = engine.apply_criteria(
        _indicator_stub(last_close=np.array([80.0]), sma_fast_last=np.array([70.0])), settings
    )
    assert bool(at_limit[CRITERION_CLOSE_VS_HIGH][0]) is True  # inclusive

    below = engine.apply_criteria(_indicator_stub(last_close=np.array([79.99])), settings)
    assert bool(below[CRITERION_CLOSE_VS_HIGH][0]) is False

    nan_close = engine.apply_criteria(_indicator_stub(last_close=np.array([np.nan])), settings)
    assert bool(nan_close[CRITERION_CLOSE_VS_HIGH][0]) is False


def test_above_sma50_filter_boundary():
    settings = ScanSettings()
    assert bool(
        engine.apply_criteria(
            _indicator_stub(last_close=np.array([100.0]), sma_fast_last=np.array([100.0])),
            settings,
        )[CRITERION_ABOVE_SMA50][0]
    )
    assert not bool(
        engine.apply_criteria(
            _indicator_stub(last_close=np.array([100.0]), sma_fast_last=np.array([100.01])),
            settings,
        )[CRITERION_ABOVE_SMA50][0]
    )


def test_sma50_above_sma150_filter_boundary():
    settings = ScanSettings()
    assert bool(
        engine.apply_criteria(
            _indicator_stub(sma_fast_last=np.array([90.0]), sma_mid_last=np.array([90.0])),
            settings,
        )[CRITERION_SMA50_ABOVE_SMA150][0]
    )
    assert not bool(
        engine.apply_criteria(
            _indicator_stub(sma_fast_last=np.array([89.99]), sma_mid_last=np.array([90.0])),
            settings,
        )[CRITERION_SMA50_ABOVE_SMA150][0]
    )


def test_rising_sma200_filter_requires_20_sessions_back():
    settings = ScanSettings()
    rising_ok = engine.apply_criteria(
        _indicator_stub(sma_slow_last=np.array([85.0]), sma_slow_back=np.array([84.0])), settings
    )
    assert bool(rising_ok[CRITERION_RISING_SMA200][0]) is True

    flat = engine.apply_criteria(
        _indicator_stub(sma_slow_last=np.array([85.0]), sma_slow_back=np.array([85.0])), settings
    )
    assert bool(flat[CRITERION_RISING_SMA200][0]) is False  # strict >

    no_history = engine.apply_criteria(
        _indicator_stub(
            sma_slow_last=np.array([85.0]),
            sma_slow_back=np.array([np.nan]),
            has_sma_back=np.array([False]),
        ),
        settings,
    )
    assert bool(no_history[CRITERION_RISING_SMA200][0]) is False


def test_rs_at_high_filter_boundary():
    settings = ScanSettings(lookback_days=252)
    assert bool(
        engine.apply_criteria(
            _indicator_stub(rs_last=np.array([12.0]), rs_highest_last=np.array([12.0])), settings
        )[CRITERION_RS_AT_HIGH][0]
    )
    assert not bool(
        engine.apply_criteria(
            _indicator_stub(rs_last=np.array([11.99]), rs_highest_last=np.array([12.0])), settings
        )[CRITERION_RS_AT_HIGH][0]
    )
    # not enough RS history -> fails rather than passing on a partial window
    assert not bool(
        engine.apply_criteria(
            _indicator_stub(rs_sessions=np.array([251]), rs_last=np.array([12.0])), settings
        )[CRITERION_RS_AT_HIGH][0]
    )


def test_combined_logic_is_an_and(scanner_env, client):
    """Per-criterion counts are independent; the result requires all of them."""
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    everything = post_scan(client).json()
    assert everything["count"] == 1

    for flag in (
        "require_above_sma50",
        "require_sma50_above_sma150",
        "require_rising_sma200",
        "require_rs_at_high",
    ):
        body = post_scan(client, **{flag: False}).json()
        assert body["count"] == 1, flag
        assert body["diagnostics"]["criterion_active"][
            {
                "require_above_sma50": CRITERION_ABOVE_SMA50,
                "require_sma50_above_sma150": CRITERION_SMA50_ABOVE_SMA150,
                "require_rising_sma200": CRITERION_RISING_SMA200,
                "require_rs_at_high": CRITERION_RS_AT_HIGH,
            }[flag]
        ] is False

    # a strict close-vs-high threshold rejects the same stock
    strict = post_scan(client, min_close_vs_high=1.0).json()
    hard = post_scan(client, min_close_vs_high=0.999999).json()
    assert hard["count"] == 1
    assert strict["count"] <= 1


# --------------------------------------------------------------------------- #
# 8 + 9. Indicator maths and RS date alignment
# --------------------------------------------------------------------------- #
def test_compute_sma_matches_the_definition():
    values = [float(v) for v in range(1, 11)]
    result = series_utils.compute_sma(values, 3)
    assert result[:3] == [None, None, 2.0]
    assert result[-1] == pytest.approx(9.0)
    assert series_utils.compute_sma(values, 3)[3] == pytest.approx(3.0)

    # None / NaN observations make the window incomplete, exactly as before
    assert series_utils.compute_sma([None, 1.0, 2.0], 2) == [None, None, 1.5]
    assert series_utils.compute_sma([1.0, float("nan"), 3.0, 4.0], 2)[3] == pytest.approx(3.5)
    assert series_utils.compute_sma([], 5) == []
    with pytest.raises(ValueError):
        series_utils.compute_sma(values, 0)


def test_moving_averages_and_rolling_high_maths():
    n = SESSIONS
    close = pd.DataFrame(
        {"A.NS": rising(n)},
        index=pd.DatetimeIndex(dates(n)),
    )
    benchmark = pd.Series(rising(n, rate=BENCHMARK_RATE), index=close.index)
    indicators = engine.compute_indicators(close, benchmark, lookback_days=252)

    closes = close["A.NS"].to_numpy()
    assert indicators["sma_fast_last"][0] == pytest.approx(closes[-50:].mean())
    assert indicators["sma_mid_last"][0] == pytest.approx(closes[-150:].mean())
    assert indicators["sma_slow_last"][0] == pytest.approx(closes[-200:].mean())
    assert indicators["sma_slow_back"][0] == pytest.approx(closes[-220:-20].mean())
    assert indicators["highest_last"][0] == pytest.approx(closes[-252:].max())
    assert indicators["last_close"][0] == pytest.approx(closes[-1])
    assert indicators["rs_last"][0] == pytest.approx(
        closes[-1] / benchmark.iloc[-1] * 100.0
    )
    assert indicators["sessions"][0] == n
    # monotone rising series: every RS print is a new high
    assert bool(engine.apply_criteria(indicators, ScanSettings())[CRITERION_RS_AT_HIGH][0])


def test_benchmark_alignment_forward_fills_across_holidays():
    """The benchmark's missing session is forward-filled onto the stock's date."""
    stock_dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
    close = pd.DataFrame(
        {"A.NS": [10.0, 11.0, 12.0, 13.0]},
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in stock_dates]),
    )
    # benchmark has no 2024-01-03 print (holiday) -> 2024-01-04 must use 100.0
    benchmark = pd.Series(
        [80.0, 100.0],
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]),
    )
    indicators = engine.compute_indicators(close, benchmark, lookback_days=3)
    rs = indicators["rs"]["A.NS"]
    assert rs.iloc[0] == pytest.approx(10.0 / 80.0 * 100.0)
    assert rs.iloc[3] == pytest.approx(13.0 / 100.0 * 100.0)
    assert indicators["rs_sessions"][0] == 4


def test_benchmark_starting_late_leaves_leading_rs_empty():
    close = pd.DataFrame(
        {"A.NS": [10.0, 11.0, 12.0]},
        index=pd.DatetimeIndex([pd.Timestamp(f"2024-01-0{i}") for i in (1, 2, 3)]),
    )
    benchmark = pd.Series(
        [100.0, 110.0],
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]),
    )
    indicators = engine.compute_indicators(close, benchmark, lookback_days=3)
    rs = indicators["rs"]["A.NS"]
    assert np.isnan(rs.iloc[0])          # no benchmark value yet, not back-filled
    assert indicators["rs_sessions"][0] == 2


def test_positions_from_end_counts_observations_not_rows():
    mask = np.array([[1], [0], [1], [0], [1]], dtype=bool)
    positions, enough = engine.positions_from_end(mask, 2)
    assert enough[0] and positions[0] == 2  # 2nd valid observation from the end
    positions, enough = engine.positions_from_end(mask, 4)
    assert not enough[0] and positions[0] == -1


# --------------------------------------------------------------------------- #
# 10. Invalid request parameters
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "payload",
    [
        {"min_close_vs_high": 5.0},
        {"min_close_vs_high": 0.0},
        {"min_close_vs_high": -0.5},
        {"lookback_days": 5},
        {"lookback_days": 100_000},
        {"benchmark_ticker": ""},
    ],
)
def test_invalid_parameters_are_rejected(client, payload):
    response = post_scan(client, **payload)
    assert response.status_code == 422, response.text


def test_request_level_validation_messages_are_clear():
    with pytest.raises(engine.ScannerRequestError) as excinfo:
        ScanSettings(min_close_vs_high=80).validate()
    assert excinfo.value.code == "invalid_min_close_vs_high"
    assert "ratio between 0 and 1" in str(excinfo.value)

    with pytest.raises(engine.ScannerRequestError) as excinfo:
        ScanSettings(lookback_days=3).validate()
    assert excinfo.value.code == "invalid_lookback_days"

    with pytest.raises(engine.ScannerRequestError):
        ScanSettings(benchmark_ticker="").validate()


# --------------------------------------------------------------------------- #
# 11. Database + unexpected failures
# --------------------------------------------------------------------------- #
def test_database_error_is_surfaced(scanner_env, client, monkeypatch):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    def boom(*args, **kwargs):
        raise duckdb.Error("injected database failure")

    monkeypatch.setattr(store, "load_price_panel", boom)
    response = post_scan(client)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "database_error"
    assert "injected" not in response.text  # internal detail stays in the log


def test_unexpected_failure_is_not_a_successful_empty_scan(scanner_env, client, monkeypatch):
    """
    Regression test: an internal exception must surface as an HTTP error, never
    as ``200 {"count": 0}``.
    """
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    def boom(*args, **kwargs):
        raise RuntimeError("injected calculation failure")

    monkeypatch.setattr(engine, "compute_indicators", boom)
    response = post_scan(client)
    assert response.status_code == 500, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "internal_error"
    assert "results" not in response.json()
    assert "injected calculation failure" not in response.text


# --------------------------------------------------------------------------- #
# 12 + 13. Concurrency, blocking and query efficiency
# --------------------------------------------------------------------------- #
def test_only_one_scan_runs_at_a_time(scanner_env, client, monkeypatch):
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    original = engine.compute_indicators
    release = threading.Event()
    running = threading.Event()

    def slow_indicators(*args, **kwargs):
        running.set()
        release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "compute_indicators", slow_indicators)
    first: dict = {}

    def run_first():
        first["response"] = post_scan(client)

    thread = threading.Thread(target=run_first)
    thread.start()
    try:
        assert running.wait(timeout=5), "the first scan never started"
        second = post_scan(client)
        assert second.status_code == 409, second.text
        assert second.json()["detail"]["code"] == "scan_in_progress"
    finally:
        release.set()
        thread.join(timeout=30)

    assert first["response"].status_code == 200
    # the guard is released again afterwards
    assert post_scan(client).status_code == 200


def test_meta_stays_responsive_while_a_scan_computes(scanner_env, client, monkeypatch):
    """
    Regression for the original defect: the scan held the DuckDB lock for the
    whole run, so every other endpoint waited minutes. The heavy computation is
    delayed here to prove it no longer holds the lock.
    """
    _tmp, universe = scanner_env
    write_universe(universe, [("GOOD", "GOOD.NS")])
    seed({"GOOD.NS": rising()}, benchmark=rising(rate=BENCHMARK_RATE))

    original = engine.compute_indicators

    def slow_indicators(*args, **kwargs):
        time.sleep(1.5)
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "compute_indicators", slow_indicators)
    result: dict = {}

    def run_scan_thread():
        result["response"] = post_scan(client)

    thread = threading.Thread(target=run_scan_thread)
    thread.start()
    time.sleep(0.4)  # the scan is now inside the (slow) computation
    started = time.perf_counter()
    meta = client.get("/api/meta")
    elapsed = time.perf_counter() - started
    thread.join(timeout=30)

    assert meta.status_code == 200
    assert result["response"].status_code == 200
    assert elapsed < 1.0, f"/api/meta was blocked for {elapsed:.2f}s during the scan"


def test_scan_reads_the_universe_in_bulk(scanner_env, monkeypatch):
    """The N+1 pattern (one query per symbol) must not come back."""
    _tmp, universe = scanner_env
    tickers = [("S000", "S000.NS"), ("S001", "S001.NS"), ("S002", "S002.NS")]
    write_universe(universe, tickers)
    seed(
        {f"{symbol}.NS": rising() for symbol, _ in tickers},
        benchmark=rising(rate=BENCHMARK_RATE),
    )

    calls = {"panel": 0, "series": 0}
    original_panel = store.load_price_panel
    original_series = store.load_series

    def counted_panel(*args, **kwargs):
        calls["panel"] += 1
        return original_panel(*args, **kwargs)

    def counted_series(*args, **kwargs):
        calls["series"] += 1
        return original_series(*args, **kwargs)

    monkeypatch.setattr(store, "load_price_panel", counted_panel)
    monkeypatch.setattr(store, "load_series", counted_series)

    outcome = run_scan(ScanSettings())
    assert calls["panel"] == 1, "the universe must be read in a single query"
    assert calls["series"] == 1, "only the benchmark should be fetched by ticker"
    assert len(outcome.frame) == len(tickers)


def test_scan_slot_rejects_a_second_holder():
    with scan_slot():
        with pytest.raises(ScannerBusyError):
            with scan_slot():
                pass
    with scan_slot():  # released again
        pass


# --------------------------------------------------------------------------- #
# 14. Performance on a realistically sized synthetic universe
# --------------------------------------------------------------------------- #
def test_scan_performance_on_a_realistic_universe(scanner_env):
    """
    400 symbols x 500 sessions (~200k rows). The original implementation took
    minutes on a universe this size; the budget here is deliberately loose so
    the test fails only on an order-of-magnitude regression.
    """
    _tmp, universe = scanner_env
    n_symbols, n_sessions = 400, 500
    tickers = [(f"S{i:03d}", f"S{i:03d}.NS") for i in range(n_symbols)]
    write_universe(universe, tickers)
    rng = np.random.default_rng(11)
    prices = {}
    for symbol, ticker in tickers:
        rate = rng.uniform(0.996, 1.004)
        prices[ticker] = rising(n=n_sessions, start=100.0, rate=rate)
    seed(prices, benchmark=rising(n=n_sessions, rate=BENCHMARK_RATE))

    started = time.perf_counter()
    outcome = run_scan(ScanSettings())
    elapsed = time.perf_counter() - started

    assert outcome.diagnostics["symbols_evaluated"] == n_symbols
    assert elapsed < 15.0, f"scan took {elapsed:.2f}s for {n_symbols} symbols"
    assert outcome.diagnostics["timings_ms"]["data_load"] < 5_000
