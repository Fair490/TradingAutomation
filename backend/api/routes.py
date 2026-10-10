"""HTTP API consumed by the React frontend."""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend import config
from backend.api import schemas
from backend.api.refresh_job import JOB
from backend.api.responses import SafeJSONResponse
from backend.compute import breadth as breadth_calc
from backend.compute import series as series_utils
from backend.loaders import store
from backend.loaders.universe import load_universe, to_yahoo_ticker

router = APIRouter(prefix="/api", default_response_class=SafeJSONResponse)

RangeQuery = Query(
    default=config.DEFAULT_RANGE,
    description="One of " + ", ".join(config.DATE_RANGES),
)


def _start_for(range_key: str) -> dt.date | None:
    if range_key not in config.DATE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown range '{range_key}'. Use one of "
            f"{', '.join(config.DATE_RANGES)}.",
        )
    return series_utils.range_start(range_key)


def _clean(value):
    """NaN / NaT -> None so the JSON stays valid."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value is pd.NaT:
        return None
    return value


def _as_date(value):
    if value is None or value is pd.NaT:
        return None
    return pd.Timestamp(value).date()


def _index_points(con, start: dt.date | None) -> tuple[list[dict], str]:
    ticker = store.get_meta(con, "index_ticker", "")
    name = store.get_meta(con, "index_name", "Index")
    if not ticker:
        return [], name
    frame = store.load_series(con, ticker, start=start)
    points = [
        {"date": _as_date(row.date), "close": _clean(float(row.close))}
        for row in frame.itertuples()
    ]
    return points, name


# --------------------------------------------------------------------------- #
# Meta / status
# --------------------------------------------------------------------------- #
@router.get("/meta", response_model=schemas.MetaResponse)
def get_meta() -> schemas.MetaResponse:
    with store.session() as con:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        n_prices = con.execute("SELECT count(*) FROM prices").fetchone()[0]
        n_tickers = con.execute("SELECT count(*) FROM tickers").fetchone()[0]
        n_stocks = con.execute(
            "SELECT count(*) FROM tickers WHERE kind = 'stock'"
        ).fetchone()[0]
        bounds = con.execute("SELECT min(date), max(date) FROM prices").fetchone()

    try:
        universe_count = len(load_universe())
    except Exception:
        universe_count = 0

    return schemas.MetaResponse(
        last_updated=meta.get("last_updated"),
        last_computed=meta.get("last_computed"),
        index_name=meta.get("index_name"),
        index_ticker=meta.get("index_ticker"),
        index_note=meta.get("index_note"),
        demo_data=meta.get("demo_data") == "1",
        has_data=n_prices > 0,
        n_prices=n_prices,
        n_tickers=n_tickers,
        n_stocks=n_stocks,
        universe_count=universe_count,
        universe_file=config.UNIVERSE_FILE.name,
        first_date=bounds[0] if bounds else None,
        last_date=bounds[1] if bounds else None,
        ranges=list(config.DATE_RANGES),
    )


@router.get("/status", response_model=schemas.StatusResponse)
def get_status() -> schemas.StatusResponse:
    with store.session() as con:
        frame = store.ticker_table(con)
    rows = []
    for row in frame.itertuples():
        rows.append(
            schemas.TickerStatus(
                ticker=row.ticker,
                symbol=row.symbol,
                name=row.name,
                kind=row.kind,
                status=row.status,
                message=row.message or "",
                first_date=_as_date(row.first_date),
                last_date=_as_date(row.last_date),
                n_rows=int(row.n_rows) if not pd.isna(row.n_rows) else 0,
            )
        )
    n_ok = sum(1 for r in rows if r.status == "ok")
    return schemas.StatusResponse(
        tickers=rows, n_ok=n_ok, n_problem=len(rows) - n_ok
    )


# --------------------------------------------------------------------------- #
# Panel 1 - advance / decline
# --------------------------------------------------------------------------- #
def _divergence_flag(points: list[schemas.AdvanceDeclinePoint], index: list[dict]) -> bool:
    """
    True when the A/D line and the benchmark index have moved in opposite
    directions for at least 3 consecutive sessions - a classic momentum warning.
    """
    if len(points) < 4 or not index:
        return False
    idx_map = {p["date"]: p["close"] for p in index if p["close"] is not None}
    recent = points[-4:]
    ad_trend = recent[-1].ad_line - recent[0].ad_line if recent[-1].ad_line is not None and recent[0].ad_line is not None else None
    if ad_trend is None:
        return False
    first_ad_date, last_ad_date = recent[0].date, recent[-1].date
    first_idx = idx_map.get(first_ad_date)
    last_idx = idx_map.get(last_ad_date)
    if first_idx is None or last_idx is None:
        return False
    idx_trend = last_idx - first_idx
    # opposite signs
    return (ad_trend > 0) != (idx_trend > 0)


@router.get("/advance-decline", response_model=schemas.AdvanceDeclineResponse)
def get_advance_decline(range: str = RangeQuery) -> schemas.AdvanceDeclineResponse:
    start = _start_for(range)
    with store.session() as con:
        frame = breadth_calc.read_advance_decline(con, start)
        index_points, index_name = _index_points(con, start)

    points = [
        schemas.AdvanceDeclinePoint(
            date=_as_date(row.date),
            advances=int(row.advances),
            declines=int(row.declines),
            unchanged=int(row.unchanged),
            ad_ratio=_clean(row.ad_ratio),
            ad_ratio_smooth=_clean(getattr(row, "ad_ratio_smooth", None)),
            ad_line=_clean(row.ad_line),
        )
        for row in frame.itertuples()
    ]
    latest_daily = points[-1].ad_ratio if points else None
    latest_avg = points[-1].ad_ratio_smooth if points else None
    return schemas.AdvanceDeclineResponse(
        points=points,
        index=index_points,
        index_name=index_name,
        smoothing_window=config.AD_SMOOTHING_WINDOW,
        latest_daily_ratio=_clean(latest_daily),
        latest_avg_ratio=_clean(latest_avg),
        divergence=_divergence_flag(points, index_points),
        footnote=config.FOOTNOTE_SURVIVORSHIP,
    )


# --------------------------------------------------------------------------- #
# Panel 2 - breadth
# --------------------------------------------------------------------------- #
@router.get("/breadth", response_model=schemas.BreadthResponse)
def get_breadth(range: str = RangeQuery) -> schemas.BreadthResponse:
    start = _start_for(range)
    with store.session() as con:
        frame = breadth_calc.read_breadth(con, start)
        full = breadth_calc.read_breadth(con, None)
        index_points, index_name = _index_points(con, start)

    points = [
        schemas.BreadthPoint(
            date=_as_date(row.date),
            pct_above=_clean(row.pct_above),
            above_below=_clean(row.above_below),
            n_valid=int(row.n_valid),
            n_above=int(row.n_above),
            n_below=int(row.n_below),
        )
        for row in frame.itertuples()
    ]

    latest = None
    if not full.empty:
        last = full.iloc[-1]
        latest = schemas.BreadthLatest(
            date=_as_date(last["date"]),
            pct_above=_clean(float(last["pct_above"])),
            above_below=_clean(float(last["above_below"]))
            if pd.notna(last["above_below"])
            else None,
            n_above=int(last["n_above"]),
            n_below=int(last["n_below"]),
            n_valid=int(last["n_valid"]),
            change_1d=_clean(series_utils.change_vs(full, "pct_above", 1)),
            change_1w=_clean(series_utils.change_vs(full, "pct_above", 5)),
        )

    return schemas.BreadthResponse(
        points=points,
        index=index_points,
        index_name=index_name,
        latest=latest,
        thresholds=schemas.Thresholds(
            overbought=config.BREADTH_OVERBOUGHT,
            midline=config.BREADTH_MIDLINE,
            oversold=config.BREADTH_OVERSOLD,
        ),
        footnote=config.FOOTNOTE_SURVIVORSHIP,
    )


# --------------------------------------------------------------------------- #
# Panel 3 - global markets
# --------------------------------------------------------------------------- #
@router.get("/global", response_model=list[schemas.GlobalCard])
def get_global() -> list[schemas.GlobalCard]:
    spark_start = dt.date.today() - dt.timedelta(days=35)
    cards: list[schemas.GlobalCard] = []
    with store.session() as con:
        # The "latest" trading date across all cards - anything older than
        # this is flagged as stale (weekend/holiday in another country).
        all_last_dates: list[dt.date] = []
        raw: list[dict] = []
        for name, ticker in config.GLOBAL_INDICES:
            snap = series_utils.last_session(con, ticker)
            frame = store.load_series(con, ticker, start=spark_start)
            spark = [
                schemas.Point(date=_as_date(r.date), value=_clean(float(r.close)))
                for r in frame.itertuples()
            ]
            full = store.load_series(con, ticker)
            stats = _series_stats(full) if not full.empty else {
                "change_1m": None, "change_1y": None, "change_5y": None,
            }
            ma_data: dict = {}
            if not full.empty:
                closes = full["close"].astype(float)
                ma50 = closes.rolling(50, min_periods=50).mean()
                ma150 = closes.rolling(150, min_periods=150).mean()
                ma_data["ma50"] = _clean(float(ma50.iloc[-1])) if len(ma50.dropna()) else None
                ma_data["ma150"] = _clean(float(ma150.iloc[-1])) if len(ma150.dropna()) else None
            raw.append({
                "name": name,
                "ticker": ticker,
                "snap": snap,
                "spark": spark,
                "stats": stats,
                "ma": ma_data,
            })
            if snap:
                all_last_dates.append(snap["date"])

        latest_date = max(all_last_dates) if all_last_dates else None
        for row in raw:
            snap = row["snap"]
            cards.append(
                schemas.GlobalCard(
                    name=row["name"],
                    ticker=row["ticker"],
                    last_close=snap["close"] if snap else None,
                    change_pct=_clean(snap["change_pct"]) if snap else None,
                    last_date=snap["date"] if snap else None,
                    stale=(
                        latest_date is not None
                        and snap is not None
                        and snap["date"] < latest_date
                    ),
                    spark=row["spark"],
                    change_1m=row["stats"].get("change_1m"),
                    change_1y=row["stats"].get("change_1y"),
                    change_5y=row["stats"].get("change_5y"),
                    unit=_unit_for(row["ticker"]),
                    ma50=row["ma"].get("ma50"),
                    ma150=row["ma"].get("ma150"),
                )
            )
    return cards


# --------------------------------------------------------------------------- #
# Panels 4 & 5 - macro and commodities
# --------------------------------------------------------------------------- #
NOTES = {"USD/INR": "Rupees per dollar — a rising line means a weaker rupee."}


def _series_stats(frame: pd.DataFrame) -> dict:
    """Per-period % changes for a daily price frame."""
    if frame.empty:
        return {"change_1m": None, "change_1y": None, "change_5y": None}
    last = float(frame["close"].iloc[-1])
    last_date = pd.to_datetime(frame["date"].iloc[-1]).date()
    out: dict[str, float | None] = {}
    for label, days in (("change_1m", 30), ("change_1y", 365), ("change_5y", 365 * 5)):
        target = last_date - dt.timedelta(days=days)
        eligible = frame.loc[pd.to_datetime(frame["date"]).dt.date <= target]
        if eligible.empty:
            out[label] = None
            continue
        base = float(eligible["close"].iloc[-1])
        out[label] = _clean((last / base - 1.0) * 100.0 if base else None)
    return out


def _moving_average_lists(frame: pd.DataFrame) -> schemas.MovingAverages | None:
    """
    Two aligned lists (ma50, ma150) with the same length as the daily price
    series. NaN at the head renders as an empty line in the chart.
    """
    if frame.empty:
        return None
    closes = frame["close"].astype(float)
    ma50 = closes.rolling(50, min_periods=50).mean()
    ma150 = closes.rolling(150, min_periods=150).mean()
    return schemas.MovingAverages(
        ma50=[_clean(float(v)) for v in ma50],
        ma150=[_clean(float(v)) for v in ma150],
    )


def _unit_for(ticker: str) -> str:
    return config.GLOBAL_UNITS.get(ticker, "price")


def _named_series(mapping, start: dt.date | None) -> schemas.SeriesResponse:
    out: list[schemas.NamedSeries] = []
    with store.session() as con:
        for name, ticker in mapping:
            # Always load the full series so we can compute the 1M/1Y/5Y
            # changes even when the displayed window is shorter (e.g. 3M).
            full = store.load_series(con, ticker)
            frame = full
            if start is not None and not full.empty:
                frame = full.loc[pd.to_datetime(full["date"]).dt.date >= start]
            points = [
                schemas.Point(date=_as_date(r.date), value=_clean(float(r.close)))
                for r in frame.itertuples()
            ]
            # US 10Y yield is expressed in percent on Yahoo; convert to bps.
            unit = _unit_for(ticker)
            values = [p.value for p in points]
            if unit == "bps":
                values = [_clean(v * 100.0) if v is not None else None for v in values]

            change = None
            non_null = [v for v in values if v is not None]
            if len(non_null) > 1 and non_null[0]:
                change = (non_null[-1] / non_null[0] - 1.0) * 100.0

            stats = _series_stats(full)
            # Compute MAs on the full series, then filter to match the display range
            ma_full = _moving_average_lists(full)
            ma_filtered = None
            if ma_full and not full.empty and not frame.empty:
                # Find the offset: how many rows were filtered out at the start
                offset = len(full) - len(frame)
                # For bps units, convert MA values to match the displayed scale
                ma50_values = ma_full.ma50[offset:]
                ma150_values = ma_full.ma150[offset:]
                if unit == "bps":
                    ma50_values = [_clean(v * 100.0) if v is not None else None for v in ma50_values]
                    ma150_values = [_clean(v * 100.0) if v is not None else None for v in ma150_values]
                ma_filtered = schemas.MovingAverages(
                    ma50=ma50_values,
                    ma150=ma150_values,
                )
            out.append(
                schemas.NamedSeries(
                    name=name,
                    ticker=ticker,
                    points=[
                        schemas.Point(date=p.date, value=v)
                        for p, v in zip(points, values)
                    ],
                    last_value=values[-1] if values else None,
                    change_pct=_clean(change),
                    note=NOTES.get(name),
                    unit=unit,
                    change_1m=stats["change_1m"],
                    change_1y=stats["change_1y"],
                    change_5y=stats["change_5y"],
                    moving_averages=ma_filtered,
                )
            )
    return schemas.SeriesResponse(series=out)


@router.get("/macro", response_model=schemas.SeriesResponse)
def get_macro(range: str = RangeQuery) -> schemas.SeriesResponse:
    return _named_series(config.MACRO_SERIES, _start_for(range))


@router.get("/commodities", response_model=schemas.SeriesResponse)
def get_commodities(range: str = RangeQuery) -> schemas.SeriesResponse:
    return _named_series(config.COMMODITIES, _start_for(range))


# --------------------------------------------------------------------------- #
# Refresh
# --------------------------------------------------------------------------- #
@router.post("/refresh", response_model=schemas.RefreshState)
def post_refresh(payload: schemas.RefreshRequest) -> schemas.RefreshState:
    if not JOB.start(full_rebuild=payload.full_rebuild):
        raise HTTPException(status_code=409, detail="A refresh is already running.")
    return schemas.RefreshState(**JOB.state())


@router.get("/refresh/status", response_model=schemas.RefreshState)
def get_refresh_status() -> schemas.RefreshState:
    return schemas.RefreshState(**JOB.state())


# --------------------------------------------------------------------------- #
# Panel 6 - sector / thematic ETFs
# --------------------------------------------------------------------------- #
def _thin(rows: list[dict], max_points: int) -> list[dict]:
    """Even stride down to ``max_points``, always keeping first and last."""
    if len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    out = [rows[int(i * step)] for i in range(max_points - 1)]
    out.append(rows[-1])
    return out


def _series_points(con, ticker: str, start: dt.date | None) -> list[dict]:
    frame = store.load_series(con, ticker, start=start)
    return [
        {"date": _as_date(r.date), "value": _clean(float(r.close))}
        for r in frame.itertuples()
    ]


def _pct_change(points: list[dict]) -> float | None:
    values = [p["value"] for p in points if p["value"] is not None]
    if len(values) < 2 or not values[0]:
        return None
    return _clean((values[-1] / values[0] - 1.0) * 100.0)


def _period_change(points: list[dict], days: int, today: dt.date) -> float | None:
    """Percent change between the last bar and the one closest to ``today - days``."""
    if not points or points[-1]["value"] is None:
        return None
    target = today - dt.timedelta(days=days)
    eligible = [p for p in points if p["date"] is not None and p["date"] <= target]
    if not eligible or eligible[-1]["value"] is None or not eligible[-1]["value"]:
        return None
    last = points[-1]["value"]
    base = eligible[-1]["value"]
    return _clean((last / base - 1.0) * 100.0)


@router.get("/etfs", response_model=schemas.EtfListResponse)
def get_etfs(range: str = RangeQuery) -> schemas.EtfListResponse:
    """
    Leaderboard for every configured ETF over the selected window.

    Along with the headline change/relative figures, each card also ships
    per-period (1M/3M/6M/1Y) stats for the ranking selector, plus the 52-week
    high distance and the distance from the 50- and 150-day moving averages.
    The ranking selector on the frontend sorts on ``periods[<range>].relative_pct``.
    """
    start = _start_for(range)
    today = dt.date.today()
    with store.session() as con:
        benchmark_ticker = store.get_meta(con, "index_ticker", "")
        benchmark_name = store.get_meta(con, "index_name", "Index")
        benchmark_points = (
            _series_points(con, benchmark_ticker, start) if benchmark_ticker else []
        )
        benchmark_change = _pct_change(benchmark_points)

        # Pre-compute the benchmark's per-period change so each ETF's relative
        # stat can be computed without re-fetching.
        benchmark_periods: dict[str, float | None] = {
            p: _period_change(
                _series_points(
                    con, benchmark_ticker, series_utils.range_start(p, today)
                ),
                config.DATE_RANGES[p],
                today,
            )
            for p in config.ETF_RANK_PERIODS
        } if benchmark_ticker else {p: None for p in config.ETF_RANK_PERIODS}

        out: list[schemas.EtfSummary] = []
        for symbol, label, group in config.ETF_SERIES:
            ticker = to_yahoo_ticker(symbol)
            points = _series_points(con, ticker, start)
            change = _pct_change(points)
            relative = (
                _clean(change - benchmark_change)
                if change is not None and benchmark_change is not None
                else None
            )
            partial = bool(
                points
                and start is not None
                and points[0]["date"] is not None
                and (points[0]["date"] - start).days > 10
            )

            # Per-period ranking stats
            periods: dict[str, schemas.EtfPeriod] = {}
            for period in config.ETF_RANK_PERIODS:
                period_start = series_utils.range_start(period, today)
                period_points = (
                    _series_points(con, ticker, period_start)
                    if period_start else points
                )
                p_change = _period_change(
                    period_points, config.DATE_RANGES[period], today,
                )
                b_change = benchmark_periods[period]
                p_relative = (
                    _clean(p_change - b_change)
                    if p_change is not None and b_change is not None
                    else None
                )
                periods[period] = schemas.EtfPeriod(
                    change_pct=p_change, relative_pct=p_relative,
                )

            # 52-week / MA snapshot stats for the card footer
            stats = series_utils.price_stats_vs_ma(con, ticker)

            out.append(
                schemas.EtfSummary(
                    symbol=symbol,
                    ticker=ticker,
                    name=label,
                    group=group,
                    last_value=points[-1]["value"] if points else None,
                    last_date=points[-1]["date"] if points else None,
                    change_pct=change,
                    relative_pct=relative,
                    first_date=points[0]["date"] if points else None,
                    partial=partial,
                    spark=_thin(points, config.ETF_SPARK_POINTS),
                    periods=periods,
                    pct_from_52w_high=_clean(stats.get("pct_from_52w_high")),
                    pct_from_50dma=_clean(stats.get("pct_from_50dma")),
                    pct_from_150dma=_clean(stats.get("pct_from_150dma")),
                )
            )

    groups: list[str] = []
    for _, _, group in config.ETF_SERIES:
        if group not in groups:
            groups.append(group)

    return schemas.EtfListResponse(
        etfs=out,
        groups=groups,
        benchmark_name=benchmark_name,
        benchmark_change_pct=benchmark_change,
        range=range,
    )


@router.get("/etfs/compare", response_model=schemas.EtfCompareResponse)
def compare_etfs(
    symbols: str = Query(..., description="Comma separated NSE symbols"),
    range: str = RangeQuery,
    benchmark: bool = Query(True, description="Include the index line"),
) -> schemas.EtfCompareResponse:
    """Full lines for the handful of ETFs the user ticked, plus the index."""
    start = _start_for(range)
    known = {symbol: label for symbol, label, _ in config.ETF_SERIES}
    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()][:8]
    unknown = [s for s in wanted if s not in known]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown ETF symbol(s): {', '.join(unknown)}"
        )

    with store.session() as con:
        series = [
            schemas.EtfSeries(
                symbol=symbol,
                name=known[symbol],
                points=_thin(
                    _series_points(con, to_yahoo_ticker(symbol), start),
                    config.ETF_CHART_POINTS,
                ),
            )
            for symbol in wanted
        ]
        benchmark_name = store.get_meta(con, "index_name", "Index")
        benchmark_series = None
        if benchmark:
            ticker = store.get_meta(con, "index_ticker", "")
            if ticker:
                points = _thin(
                    _series_points(con, ticker, start), config.ETF_CHART_POINTS
                )
                if points:
                    benchmark_series = schemas.EtfSeries(
                        symbol=ticker, name=benchmark_name, points=points
                    )

    return schemas.EtfCompareResponse(
        series=series,
        benchmark=benchmark_series,
        benchmark_name=benchmark_name,
        range=range,
    )


# --------------------------------------------------------------------------- #
# RS benchmark series (drives the Relative Strength indicator)
# --------------------------------------------------------------------------- #
@router.get("/rs-benchmark")
def get_rs_benchmark(
    ticker: str = Query(
        default=config.RS_BENCHMARKS[0][1],
        description="One of " + ", ".join(t for _, t in config.RS_BENCHMARKS),
    ),
    range: str = RangeQuery,
) -> dict:
    """
    Return the daily close series for one of the configured RS benchmarks.
    The frontend uses this to compute CRS = close / benchmark_close for any
    other series, then colours the result green/red by direction and marks
    the all-time-high of CRS.
    """
    known = {t for _, t in config.RS_BENCHMARKS}
    if ticker not in known:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown RS benchmark '{ticker}'. Use one of {sorted(known)}.",
        )
    start = _start_for(range)
    name = next(n for n, t in config.RS_BENCHMARKS if t == ticker)
    with store.session() as con:
        points = _series_points(con, ticker, start)
    return {
        "ticker": ticker,
        "name": name,
        "points": points,
        "range": range,
    }


# --------------------------------------------------------------------------- #
# Global price chart (combined, with MAs - powers the chart view in the
# Global panel; complements the cards view which shows 1M spark + daily pill)
# --------------------------------------------------------------------------- #
@router.get("/global-chart", response_model=schemas.SeriesResponse)
def get_global_chart(range: str = RangeQuery) -> schemas.SeriesResponse:
    """
    All global price indices as a SeriesResponse. VIX is excluded because it
    lives on a completely different scale (10-30) from the indices (10k-40k)
    and would be invisible on a combined chart.
    """
    price_indices = [(n, t) for n, t in config.GLOBAL_INDICES if t != "^INDIAVIX"]
    return _named_series(price_indices, _start_for(range))
