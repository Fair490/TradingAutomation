"""Small helpers shared by the macro / commodity / global panels."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from backend import config
from backend.loaders import store


def range_start(range_key: str, today: dt.date | None = None) -> dt.date | None:
    """Convert a range button ('1M', '5Y', …) into a start date."""
    days = config.DATE_RANGES.get(range_key)
    if days is None:
        return None
    return (today or dt.date.today()) - dt.timedelta(days=days)


def load_named_series(
    con, mapping: list[tuple[str, str]], start: dt.date | None = None,
    forward_fill: bool = False,
) -> pd.DataFrame:
    """
    Return a wide frame indexed by date with one column per display name.
    Holiday gaps in macro / commodity series may be forward-filled for display
    (never for stock prices).
    """
    frames = []
    for name, ticker in mapping:
        one = store.load_series(con, ticker, start=start)
        if one.empty:
            continue
        one = one[["date", "close"]].rename(columns={"close": name})
        one["date"] = pd.to_datetime(one["date"])
        frames.append(one.set_index("date"))
    if not frames:
        return pd.DataFrame()
    wide = pd.concat(frames, axis=1).sort_index()
    if forward_fill:
        wide = wide.ffill()
    return wide


def normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Rebase every column to 100 at the first valid observation."""
    if frame.empty:
        return frame
    base = frame.apply(lambda col: col.dropna().iloc[0] if col.notna().any() else pd.NA)
    return frame.divide(base, axis=1) * 100.0


def last_session(con, ticker: str) -> dict | None:
    """Last close, % change vs the previous close, and the trading date."""
    frame = store.load_series(con, ticker)
    if frame.empty:
        return None
    frame = frame.dropna(subset=["close"])
    if frame.empty:
        return None
    last = frame.iloc[-1]
    prev = frame.iloc[-2] if len(frame) > 1 else None
    change = None
    if prev is not None and prev["close"]:
        change = (last["close"] / prev["close"] - 1.0) * 100.0
    return {
        "date": pd.to_datetime(last["date"]).date(),
        "close": float(last["close"]),
        "change_pct": change,
    }


def change_vs(frame: pd.DataFrame, column: str, periods: int) -> float | None:
    """Difference between the latest value and the one ``periods`` rows back."""
    series = frame[column].dropna()
    if len(series) <= periods:
        return None
    return float(series.iloc[-1] - series.iloc[-1 - periods])


# --------------------------------------------------------------------------- #
# Moving averages and per-period stats (used on every price chart)
# --------------------------------------------------------------------------- #
def add_moving_averages(frame: pd.DataFrame, windows: tuple[int, ...]) -> pd.DataFrame:
    """
    Append simple moving-average columns for each window. Columns are named
    ``ma_<window>`` and placed alongside the existing price columns. NaN at
    the head is intentional - the frontend renders the MA only once enough
    observations exist.
    """
    if frame.empty or not windows:
        return frame
    for w in windows:
        col = f"ma_{w}"
        if "close" in frame.columns:
            frame[col] = frame["close"].rolling(window=w, min_periods=w).mean()
        else:
            # wide frame: one MA column per existing column
            for existing in frame.columns:
                frame[f"{existing}_ma{w}"] = (
                    frame[existing].rolling(window=w, min_periods=w).mean()
                )
    return frame


def per_period_change_pct(
    con, ticker: str, today: dt.date | None = None,
) -> dict[str, float | None]:
    """
    Percent change over each of the configured ranking periods (1M / 3M / 6M /
    1Y). Returns a dict keyed by the period name. The calculation uses the
    closest available bar within ±3 calendar days of the target start, so a
    holiday doesn't drop a period.
    """
    frame = store.load_series(con, ticker)
    if frame.empty:
        return {p: None for p in config.ETF_RANK_PERIODS}
    last_date = pd.to_datetime(frame["date"].iloc[-1]).date()
    last_close = float(frame["close"].iloc[-1])
    today = today or dt.date.today()
    out: dict[str, float | None] = {}
    for period in config.ETF_RANK_PERIODS:
        days = config.DATE_RANGES.get(period)
        if days is None:
            out[period] = None
            continue
        target = today - dt.timedelta(days=days)
        if target > last_date:
            out[period] = None
            continue
        # find closest row to the target date
        dates = pd.to_datetime(frame["date"])
        idx = (dates - pd.to_datetime(target)).abs().idxmin()
        # but only take rows up to the target (don't use future data)
        eligible = frame.loc[dates <= pd.to_datetime(target)]
        if eligible.empty:
            out[period] = None
            continue
        base = float(eligible["close"].iloc[-1])
        if base:
            out[period] = (last_close / base - 1.0) * 100.0
        else:
            out[period] = None
    return out


def price_stats_vs_ma(con, ticker: str) -> dict:
    """
    For one ticker: the 52-week high / low, last close, and the distance from
    each, plus the distance from the 50-DMA and 150-DMA if they exist.
    Returned numbers are in percent (e.g. +4.2 means 4.2% above the 50-DMA).
    """
    frame = store.load_series(con, ticker)
    if frame.empty:
        return {}
    closes = frame["close"].astype(float).dropna()
    if closes.empty:
        return {}
    last = float(closes.iloc[-1])
    last_date = pd.to_datetime(frame["date"].iloc[-1]).date()
    # 52-week = last 252 trading rows (rough proxy) or last 365 calendar days
    one_year_ago = last_date - dt.timedelta(days=365)
    recent = frame.loc[pd.to_datetime(frame["date"]).dt.date >= one_year_ago]
    recent_closes = recent["close"].astype(float).dropna()
    if recent_closes.empty:
        return {}
    high_52w = float(recent_closes.max())
    low_52w = float(recent_closes.min())
    ma50 = float(closes.rolling(50, min_periods=50).mean().iloc[-1]) \
        if len(closes) >= 50 else None
    ma150 = float(closes.rolling(150, min_periods=150).mean().iloc[-1]) \
        if len(closes) >= 150 else None
    return {
        "last_close": last,
        "last_date": last_date,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_from_52w_high": (last / high_52w - 1.0) * 100.0 if high_52w else None,
        "pct_from_52w_low": (last / low_52w - 1.0) * 100.0 if low_52w else None,
        "ma50": ma50,
        "ma150": ma150,
        "pct_from_50dma": (last / ma50 - 1.0) * 100.0 if ma50 else None,
        "pct_from_150dma": (last / ma150 - 1.0) * 100.0 if ma150 else None,
    }


def compute_sma(values: list[float | None] | pd.Series, window: int) -> list[float | None]:
    """
    Compute Simple Moving Average.
    
    Args:
        values: List or Series of numeric values
        window: Window size for SMA
    
    Returns:
        List of SMA values (None for insufficient data)
    """
    import numpy as np
    
    if isinstance(values, pd.Series):
        values = values.tolist()
    
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            window_values = values[i - window + 1:i + 1]
            valid_values = [v for v in window_values if v is not None and not np.isnan(v)]
            if len(valid_values) == window:
                result.append(sum(valid_values) / window)
            else:
                result.append(None)
    
    return result
