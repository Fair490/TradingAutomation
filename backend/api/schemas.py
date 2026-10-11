"""Pydantic response models - these double as the contract for the frontend."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class Point(BaseModel):
    date: dt.date
    value: float | None = None


class IndexPoint(BaseModel):
    date: dt.date
    close: float | None = None


class AdvanceDeclinePoint(BaseModel):
    date: dt.date
    advances: int
    declines: int
    unchanged: int
    ad_ratio: float | None = None
    ad_ratio_smooth: float | None = None
    ad_line: float | None = None


class BreadthPoint(BaseModel):
    date: dt.date
    pct_above: float | None = None
    above_below: float | None = None
    n_valid: int
    n_above: int
    n_below: int


class BreadthLatest(BaseModel):
    date: dt.date
    pct_above: float | None = None
    above_below: float | None = None
    n_above: int
    n_below: int
    n_valid: int
    change_1d: float | None = None
    change_1w: float | None = None


class Thresholds(BaseModel):
    overbought: float
    midline: float
    oversold: float


class BreadthResponse(BaseModel):
    points: list[BreadthPoint]
    index: list[IndexPoint]
    index_name: str
    latest: BreadthLatest | None = None
    thresholds: Thresholds
    footnote: str


class AdvanceDeclineResponse(BaseModel):
    points: list[AdvanceDeclinePoint]
    index: list[IndexPoint]
    index_name: str
    smoothing_window: int
    # Latest-session helpers for the headline card (frontend could compute these
    # itself, but shipping them once avoids a second round-trip).
    latest_daily_ratio: float | None = None
    latest_avg_ratio: float | None = None
    # True when the A/D line and the index have moved in opposite directions
    # for at least 3 consecutive sessions - the UI flags this as a divergence.
    divergence: bool = False
    footnote: str


class GlobalCard(BaseModel):
    name: str
    ticker: str
    last_close: float | None = None
    change_pct: float | None = None       # daily change, shown in the pill
    last_date: dt.date | None = None      # the bar's actual trading date
    stale: bool = False                   # last_date differs from latest global
    spark: list[Point] = []               # 1-month sparkline
    # Period changes vs the last bar. None when the series lacks that history.
    change_1m: float | None = None
    change_1y: float | None = None
    change_5y: float | None = None
    # Display unit (e.g. "USD/oz", "₹ per $", "bps", "index"). Default is
    # "price" and the frontend shows it as-is.
    unit: str = "price"
    # Moving averages on the 1-year view - the frontend uses these for the
    # 50/150 DMA toggle on the global cards.
    ma50: float | None = None
    ma150: float | None = None


class MovingAverages(BaseModel):
    """MA columns on the daily price series, same length as ``points``."""
    ma50: list[float | None] = []
    ma150: list[float | None] = []


class NamedSeries(BaseModel):
    name: str
    ticker: str
    points: list[Point]
    last_value: float | None = None
    change_pct: float | None = None
    note: str | None = None
    unit: str = "price"
    # 1-month / 1-year / 5-year change in the same unit as the series.
    change_1m: float | None = None
    change_1y: float | None = None
    change_5y: float | None = None
    # Moving-average overlay points (same x-axis as ``points``).
    moving_averages: MovingAverages | None = None


class SeriesResponse(BaseModel):
    series: list[NamedSeries]


class EtfPeriod(BaseModel):
    """Performance stats for one ETF over a single ranking window."""
    change_pct: float | None = None
    relative_pct: float | None = None    # minus the benchmark's over the same window


class EtfSummary(BaseModel):
    symbol: str
    ticker: str
    name: str
    group: str
    last_value: float | None = None
    last_date: dt.date | None = None
    change_pct: float | None = None       # performance over the selected range
    relative_pct: float | None = None     # change_pct minus the benchmark's
    first_date: dt.date | None = None     # listing date inside the range
    partial: bool = False                 # history shorter than the range
    spark: list[Point] = []
    # Ranking helper: change + relative for each of 1M/3M/6M/1Y
    periods: dict[str, EtfPeriod] = {}
    # Snapshot stats shown on the card footer
    pct_from_52w_high: float | None = None
    pct_from_50dma: float | None = None
    pct_from_150dma: float | None = None


class EtfListResponse(BaseModel):
    etfs: list[EtfSummary]
    groups: list[str]
    benchmark_name: str
    benchmark_change_pct: float | None = None
    range: str


class EtfSeries(BaseModel):
    symbol: str
    name: str
    points: list[Point]


class EtfCompareResponse(BaseModel):
    series: list[EtfSeries]
    benchmark: EtfSeries | None = None
    benchmark_name: str
    range: str


class MetaResponse(BaseModel):
    last_updated: dt.datetime | None = None
    last_computed: dt.datetime | None = None
    index_name: str | None = None
    index_ticker: str | None = None
    index_note: str | None = None
    demo_data: bool = False
    has_data: bool = False
    n_prices: int = 0
    n_tickers: int = 0
    n_stocks: int = 0
    universe_count: int = 0
    universe_file: str = ""
    first_date: dt.date | None = None
    last_date: dt.date | None = None
    ranges: list[str] = []


class TickerStatus(BaseModel):
    ticker: str
    symbol: str | None = None
    name: str | None = None
    kind: str | None = None
    status: str | None = None
    message: str | None = None
    first_date: dt.date | None = None
    last_date: dt.date | None = None
    n_rows: int | None = None


class StatusResponse(BaseModel):
    tickers: list[TickerStatus]
    n_ok: int
    n_problem: int


class RefreshRequest(BaseModel):
    full_rebuild: bool = False


class RefreshState(BaseModel):
    running: bool = False
    progress: float = 0.0
    message: str = ""
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    ok: bool | None = None
    summary: str | None = None
    rows_added: int = 0
    tickers_updated: int = 0
    failures: list[list[str]] = []
    error: str | None = None
