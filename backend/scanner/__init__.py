"""
Stock scanner with technical criteria.

Implements the scanner logic with hard rules and flags as specified.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from backend.compute.series import compute_sma
from backend.loaders.store import load_series, session
from backend.loaders.universe import load_universe


def scan_stocks(
    benchmark_ticker: str = "^CRSLDX",
    min_close_vs_high: float = 0.80,
    require_above_sma50: bool = True,
    require_sma50_above_sma150: bool = True,
    require_rising_sma200: bool = True,
    require_rs_at_high: bool = True,
    lookback_days: int = 252,
) -> pd.DataFrame:
    """
    Scan universe stocks against technical criteria.
    
    Args:
        benchmark_ticker: Benchmark ticker for RS calculation (default: Nifty 500)
        min_close_vs_high: Minimum ratio of close to 252-day high (default: 0.80)
        require_above_sma50: Require close >= 50-day SMA
        require_sma50_above_sma150: Require SMA50 >= SMA150
        require_rising_sma200: Require SMA200 today > SMA200 20 days ago
        require_rs_at_high: Require RS >= highest RS in last 252 days
        lookback_days: Number of trading days for lookback (default: 252)
    
    Returns:
        DataFrame with scan results including all criteria and flags
    """
    # Load universe
    universe = load_universe()
    if not universe:  # Empty list
        return pd.DataFrame()
    
    # Load benchmark data
    with session() as con:
        benchmark_df = load_series(con, benchmark_ticker)
    
    if benchmark_df.empty:
        return pd.DataFrame()
    
    benchmark_df = benchmark_df.sort_values("date").reset_index(drop=True)
    benchmark_close = benchmark_df.set_index("date")["close"]
    
    results = []
    
    with session() as con:
        for stock in universe:
            ticker = stock.ticker
            symbol = stock.symbol
            name = stock.name
            
            # Load stock data
            stock_df = load_series(con, ticker)
            if stock_df.empty or len(stock_df) < lookback_days:
                continue
            
            stock_df = stock_df.sort_values("date").reset_index(drop=True)
            
            # Calculate indicators
            close = stock_df["close"].values
            high = stock_df["high"].values
            dates = stock_df["date"].values
            
            # 1. Close vs 252-day high
            highest_high_252 = pd.Series(high).rolling(window=lookback_days, min_periods=1).max().values
            close_vs_high = close[-1] / highest_high_252[-1] if highest_high_252[-1] > 0 else 0
            passes_close_vs_high = close_vs_high >= min_close_vs_high
            
            # 2. Close >= 50-day SMA
            sma50 = compute_sma(close, 50)
            passes_above_sma50 = close[-1] >= sma50[-1] if sma50[-1] is not None else False
            
            # 3. SMA50 >= SMA150
            sma150 = compute_sma(close, 150)
            passes_sma50_above_sma150 = (
                sma50[-1] >= sma150[-1] 
                if sma50[-1] is not None and sma150[-1] is not None 
                else False
            )
            
            # 4. SMA200 today > SMA200 20 days ago
            sma200 = compute_sma(close, 200)
            if len(sma200) >= 21 and sma200[-1] is not None and sma200[-21] is not None:
                passes_rising_sma200 = sma200[-1] > sma200[-21]
            else:
                passes_rising_sma200 = False
            
            # 5. RS at 252-day high
            # Calculate RS line
            stock_close_series = pd.Series(close, index=pd.to_datetime(dates))
            aligned_benchmark = benchmark_close.reindex(stock_close_series.index).ffill()
            rs_line = (stock_close_series / aligned_benchmark * 100).values
            
            # Filter out NaN values
            valid_rs = ~np.isnan(rs_line)
            if valid_rs.sum() >= lookback_days:
                rs_valid = rs_line[valid_rs]
                highest_rs_252 = pd.Series(rs_valid).rolling(window=lookback_days, min_periods=1).max().values
                rs_at_high = rs_valid[-1] >= highest_rs_252[-1] if highest_rs_252[-1] > 0 else False
            else:
                rs_at_high = False
            
            passes_rs_at_high = rs_at_high
            
            # Calculate Rising_RS flag
            if len(rs_line) >= 21 and not np.isnan(rs_line[-1]) and not np.isnan(rs_line[-21]):
                rising_rs = rs_line[-1] > rs_line[-21]
            else:
                rising_rs = False
            
            # Check if passes all hard rules
            passes_all = (
                (not require_above_sma50 or passes_above_sma50) and
                (not require_sma50_above_sma150 or passes_sma50_above_sma150) and
                (not require_rising_sma200 or passes_rising_sma200) and
                (not require_rs_at_high or passes_rs_at_high) and
                passes_close_vs_high
            )
            
            if passes_all:
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "ticker": ticker,
                    "close": close[-1],
                    "close_vs_high_252": round(close_vs_high * 100, 2),
                    "sma50": round(sma50[-1], 2) if sma50[-1] is not None else None,
                    "sma150": round(sma150[-1], 2) if sma150[-1] is not None else None,
                    "sma200": round(sma200[-1], 2) if sma200[-1] is not None else None,
                    "rs": round(rs_line[-1], 2) if not np.isnan(rs_line[-1]) else None,
                    "rising_rs": rising_rs,
                    "passes_close_vs_high": passes_close_vs_high,
                    "passes_above_sma50": passes_above_sma50,
                    "passes_sma50_above_sma150": passes_sma50_above_sma150,
                    "passes_rising_sma200": passes_rising_sma200,
                    "passes_rs_at_high": passes_rs_at_high,
                })
    
    return pd.DataFrame(results)
