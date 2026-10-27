"""
NSE Stock Scanner - Technical Analysis Based Stock Screener
Scans Indian equities from NSE for technical criteria and relative strength.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import pandas as pd
import yfinance as yf
from pathlib import Path

# ============================================================================
# CONFIGURATION - Adjust these parameters as needed
# ============================================================================

# File paths
UNIVERSE_FILE = "backend/data/universe.xlsx"
UNIVERSE_COLUMN = "Symbol"  # Column name in the Excel file
OUTPUT_DIR = "backend/data/scanner_output"

# Technical parameters
EMA_FAST = 50
EMA_SLOW = 150
HIGH_LOOKBACK = 260  # Trading days for 52-week high
HIGH_THRESHOLD = 0.70  # Close must be >= this % of 52-week high
RS_LOOKBACK = 126  # Trading days for RS score calculation
MIN_BARS = 260  # Minimum bars required for a stock to be scanned

# Benchmark
BENCHMARK_TICKER = "^CRSLDX"  # Nifty 500

# Download settings
CALENDAR_DAYS = 800  # Calendar days to download (for EMA warmup)
BATCH_SIZE = 50  # Stocks per batch
SLEEP_BETWEEN_BATCHES = 1  # Seconds between batches
MAX_RETRIES = 3  # Retries per stock

# Market hours (IST)
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scanner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_universe() -> List[str]:
    """
    Load universe from Excel or CSV file and convert to yfinance format.
    Supports both .xlsx and .csv formats with automatic fallback.
    
    Returns:
        List of tickers in yfinance format (e.g., "RELIANCE.NS")
    """
    logger.info(f"Loading universe from {UNIVERSE_FILE}")
    
    if not os.path.exists(UNIVERSE_FILE):
        # Try CSV fallback if Excel file not found
        csv_fallback = UNIVERSE_FILE.replace('.xlsx', '.csv')
        if os.path.exists(csv_fallback):
            logger.info(f"Excel file not found, falling back to CSV: {csv_fallback}")
            universe_file = csv_fallback
        else:
            raise FileNotFoundError(f"Universe file not found: {UNIVERSE_FILE} (also tried {csv_fallback})")
    else:
        universe_file = UNIVERSE_FILE
    
    # Read file based on extension
    try:
        if universe_file.endswith('.csv'):
            df = pd.read_csv(universe_file)
        elif universe_file.endswith('.xlsx') or universe_file.endswith('.xls'):
            df = pd.read_excel(universe_file)
        else:
            # Try CSV first, then Excel
            try:
                df = pd.read_csv(universe_file)
            except:
                df = pd.read_excel(universe_file)
    except Exception as e:
        raise ValueError(f"Failed to read universe file {universe_file}: {e}. Make sure openpyxl is installed for Excel files: pip install openpyxl")
    
    # Check if column exists
    if UNIVERSE_COLUMN not in df.columns:
        raise ValueError(f"Column '{UNIVERSE_COLUMN}' not found in universe file. Available columns: {df.columns.tolist()}")
    
    # Extract symbols, strip whitespace, drop duplicates and blanks
    symbols = df[UNIVERSE_COLUMN].astype(str).str.strip()
    symbols = symbols[symbols != '']
    symbols = symbols[symbols != 'nan']
    symbols = symbols.drop_duplicates()
    
    # Convert to yfinance format
    tickers = [f"{symbol}.NS" for symbol in symbols]
    
    logger.info(f"Loaded {len(tickers)} unique tickers from universe")
    return tickers


def download_benchmark_data() -> pd.Series:
    """
    Download benchmark (Nifty 500) data.
    
    Returns:
        Series with benchmark close prices indexed by date
    """
    logger.info(f"Downloading benchmark data: {BENCHMARK_TICKER}")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=CALENDAR_DAYS)
    
    for attempt in range(MAX_RETRIES):
        try:
            benchmark = yf.download(
                BENCHMARK_TICKER,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                progress=False
            )
            
            if benchmark.empty:
                raise ValueError("No data returned for benchmark")
            
            # Use Close column
            close = benchmark['Close'].squeeze()
            logger.info(f"Benchmark data loaded: {len(close)} days from {close.index[0].date()} to {close.index[-1].date()}")
            return close
            
        except Exception as e:
            logger.warning(f"Benchmark download attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
    
    raise RuntimeError(f"Failed to download benchmark data after {MAX_RETRIES} attempts")


def download_stock_data(tickers: List[str]) -> Tuple[Dict[str, pd.DataFrame], List[str], List[str]]:
    """
    Download stock data in batches with retry logic.
    
    Args:
        tickers: List of ticker symbols
        
    Returns:
        Tuple of (stock_data_dict, failed_tickers, skipped_tickers)
    """
    logger.info(f"Downloading data for {len(tickers)} stocks in batches of {BATCH_SIZE}")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=CALENDAR_DAYS)
    
    stock_data = {}
    failed_tickers = []
    skipped_tickers = []
    
    # Process in batches
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
        
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} stocks)")
        
        # Download batch
        for attempt in range(MAX_RETRIES):
            try:
                data = yf.download(
                    batch,
                    start=start_date,
                    end=end_date,
                    auto_adjust=True,
                    group_by='ticker',
                    threads=True,
                    progress=False
                )
                
                # Process each ticker in the batch
                for ticker in batch:
                    try:
                        if len(batch) == 1:
                            # Single ticker case
                            ticker_data = data
                        else:
                            # Multiple tickers case
                            ticker_data = data[ticker]
                        
                        # Check if data is valid
                        if ticker_data.empty or len(ticker_data) < MIN_BARS:
                            skipped_tickers.append(ticker)
                            logger.debug(f"Skipped {ticker}: insufficient data ({len(ticker_data)} bars)")
                            continue
                        
                        # Drop incomplete current day if market is still open
                        ticker_data = drop_incomplete_candle(ticker_data)
                        
                        stock_data[ticker] = ticker_data
                        
                    except Exception as e:
                        logger.warning(f"Error processing {ticker}: {e}")
                        skipped_tickers.append(ticker)
                
                break  # Success, move to next batch
                
            except Exception as e:
                logger.warning(f"Batch download attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
                else:
                    logger.error(f"Batch download failed after {MAX_RETRIES} attempts")
                    failed_tickers.extend(batch)
        
        # Sleep between batches to avoid rate limits
        if i + BATCH_SIZE < len(tickers):
            time.sleep(SLEEP_BETWEEN_BATCHES)
    
    logger.info(f"Download complete: {len(stock_data)} stocks loaded, {len(skipped_tickers)} skipped, {len(failed_tickers)} failed")
    return stock_data, failed_tickers, skipped_tickers


def drop_incomplete_candle(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop incomplete current day candle if market is still open.
    
    Args:
        df: DataFrame with DatetimeIndex
        
    Returns:
        DataFrame with incomplete candle removed if applicable
    """
    if df.empty:
        return df
    
    now = datetime.now()
    last_date = df.index[-1]
    
    # Check if last candle is today and market is still open
    if last_date.date() == now.date():
        if now.hour < MARKET_CLOSE_HOUR or (now.hour == MARKET_CLOSE_HOUR and now.minute < MARKET_CLOSE_MINUTE):
            # Market is still open, drop the incomplete candle
            return df.iloc[:-1]
    
    return df

# ============================================================================
# INDICATOR CALCULATION FUNCTIONS
# ============================================================================

def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.
    
    Args:
        series: Price series
        span: EMA period
        
    Returns:
        EMA series
    """
    return series.ewm(span=span, adjust=False).mean()


def calculate_52week_high(df: pd.DataFrame, lookback: int = 260) -> float:
    """
    Calculate 52-week high (max of High over lookback period).
    
    Args:
        df: DataFrame with 'High' column
        lookback: Number of trading days to look back
        
    Returns:
        52-week high value
    """
    if 'High' not in df.columns or len(df) < lookback:
        return None
    
    return df['High'].tail(lookback).max()


def calculate_rs_score(stock_close: pd.Series, benchmark_close: pd.Series, lookback: int = 126) -> Tuple[float, float, float]:
    """
    Calculate Relative Strength score.
    
    Args:
        stock_close: Stock close prices
        benchmark_close: Benchmark close prices
        lookback: RS lookback period
        
    Returns:
        Tuple of (rs_ratio_today, rs_score_percent, rs_ratio_lookback)
    """
    # Align on common dates
    common_dates = stock_close.index.intersection(benchmark_close.index)
    if len(common_dates) < lookback:
        return None, None, None
    
    stock_aligned = stock_close.loc[common_dates]
    benchmark_aligned = benchmark_close.loc[common_dates]
    
    # Calculate RS ratio
    rs_ratio = stock_aligned / benchmark_aligned
    
    # Current RS ratio
    rs_today = rs_ratio.iloc[-1]
    
    # RS ratio lookback days ago
    rs_lookback = rs_ratio.iloc[-lookback]
    
    # RS score = percentage change
    rs_score = ((rs_today / rs_lookback) - 1) * 100
    
    return rs_today, rs_score, rs_lookback

# ============================================================================
# SCANNER LOGIC
# ============================================================================

def scan_stocks(
    stock_data: Dict[str, pd.DataFrame],
    benchmark_close: pd.Series
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Scan stocks against technical criteria.
    
    Args:
        stock_data: Dictionary of stock DataFrames
        benchmark_close: Benchmark close prices
        
    Returns:
        Tuple of (passing_stocks_df, rs_percentile_series)
    """
    logger.info("Scanning stocks against criteria")
    
    results = []
    all_rs_scores = {}  # For percentile calculation
    
    for ticker, df in stock_data.items():
        try:
            # Skip if not enough data
            if len(df) < MIN_BARS:
                continue
            
            # Extract latest values
            latest = df.iloc[-1]
            close = latest['Close']
            
            # Calculate EMAs
            ema50 = calculate_ema(df['Close'], EMA_FAST)
            ema150 = calculate_ema(df['Close'], EMA_SLOW)
            
            ema50_latest = ema50.iloc[-1]
            ema150_latest = ema150.iloc[-1]
            
            # Calculate 52-week high
            high_52w = calculate_52week_high(df, HIGH_LOOKBACK)
            if high_52w is None:
                continue
            
            # Calculate RS
            rs_ratio, rs_score, _ = calculate_rs_score(df['Close'], benchmark_close, RS_LOOKBACK)
            if rs_score is None:
                continue
            
            # Store RS score for percentile calculation
            symbol = ticker.replace('.NS', '')
            all_rs_scores[symbol] = rs_score
            
            # Check conditions
            cond_1 = close >= ema50_latest  # Close >= EMA50
            cond_2 = close >= HIGH_THRESHOLD * high_52w  # Close >= 0.70 * 52W High
            cond_3 = ema50_latest >= ema150_latest  # EMA50 >= EMA150
            
            if cond_1 and cond_2 and cond_3:
                # Calculate additional metrics
                pct_below_high = ((close / high_52w) - 1) * 100
                pct_vs_ema50 = ((close / ema50_latest) - 1) * 100
                
                results.append({
                    'Symbol': symbol,
                    'Close': close,
                    'EMA50': ema50_latest,
                    'EMA150': ema150_latest,
                    '52W_High': high_52w,
                    'Pct_Below_52W_High': pct_below_high,
                    'Close_vs_EMA50_Pct': pct_vs_ema50,
                    'RS_Ratio': rs_ratio,
                    'RS_Score_Pct': rs_score
                })
        
        except Exception as e:
            logger.warning(f"Error scanning {ticker}: {e}")
            continue
    
    # Convert to DataFrame
    if not results:
        logger.warning("No stocks passed the criteria")
        return pd.DataFrame(), pd.Series(all_rs_scores)
    
    results_df = pd.DataFrame(results)
    
    # Calculate RS percentile for all stocks
    rs_percentile_series = pd.Series(all_rs_scores).rank(pct=True) * 100
    
    # Add RS percentile to passing stocks
    results_df['RS_Percentile'] = results_df['Symbol'].map(rs_percentile_series).round(0).astype(int)
    
    # Sort by RS score and add rank
    results_df = results_df.sort_values('RS_Score_Pct', ascending=False).reset_index(drop=True)
    results_df.insert(0, 'Rank', range(1, len(results_df) + 1))
    
    logger.info(f"Scan complete: {len(results_df)} stocks passed criteria")
    return results_df, rs_percentile_series


def save_results(df: pd.DataFrame, output_dir: str = OUTPUT_DIR) -> Tuple[str, str]:
    """
    Save results to CSV and Excel files.
    
    Args:
        df: Results DataFrame
        output_dir: Output directory
        
    Returns:
        Tuple of (csv_path, excel_path)
    """
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate filename with date
    date_str = datetime.now().strftime('%Y-%m-%d')
    base_filename = f"scan_results_{date_str}"
    
    # Save to CSV
    csv_path = os.path.join(output_dir, f"{base_filename}.csv")
    df.to_csv(csv_path, index=False)
    logger.info(f"Results saved to {csv_path}")
    
    # Save to Excel
    excel_path = os.path.join(output_dir, f"{base_filename}.xlsx")
    df.to_excel(excel_path, index=False, sheet_name='Scan Results')
    logger.info(f"Results saved to {excel_path}")
    
    return csv_path, excel_path


def print_summary(
    results_df: pd.DataFrame,
    total_scanned: int,
    skipped_tickers: List[str],
    failed_tickers: List[str],
    top_n: int = 25
) -> None:
    """
    Print summary to console.
    
    Args:
        results_df: Results DataFrame
        total_scanned: Total number of stocks scanned
        skipped_tickers: List of skipped tickers
        failed_tickers: List of failed tickers
        top_n: Number of top results to display
    """
    print("\n" + "="*80)
    print("SCAN RESULTS SUMMARY")
    print("="*80)
    print(f"Total stocks in universe: {total_scanned + len(skipped_tickers) + len(failed_tickers)}")
    print(f"Stocks scanned: {total_scanned}")
    print(f"Stocks passed criteria: {len(results_df)}")
    print(f"Stocks skipped (insufficient data): {len(skipped_tickers)}")
    print(f"Stocks failed (download error): {len(failed_tickers)}")
    print("="*80)
    
    if not results_df.empty:
        print(f"\nTOP {min(top_n, len(results_df))} STOCKS:")
        print("-"*80)
        
        # Format for display
        display_cols = ['Rank', 'Symbol', 'Close', 'EMA50', 'EMA150', '52W_High', 
                       'Pct_Below_52W_High', 'Close_vs_EMA50_Pct', 'RS_Ratio', 
                       'RS_Score_Pct', 'RS_Percentile']
        
        display_df = results_df[display_cols].head(top_n).copy()
        
        # Format numbers
        display_df['Close'] = display_df['Close'].map(lambda x: f"₹{x:.2f}")
        display_df['EMA50'] = display_df['EMA50'].map(lambda x: f"₹{x:.2f}")
        display_df['EMA150'] = display_df['EMA150'].map(lambda x: f"₹{x:.2f}")
        display_df['52W_High'] = display_df['52W_High'].map(lambda x: f"₹{x:.2f}")
        display_df['Pct_Below_52W_High'] = display_df['Pct_Below_52W_High'].map(lambda x: f"{x:.2f}%")
        display_df['Close_vs_EMA50_Pct'] = display_df['Close_vs_EMA50_Pct'].map(lambda x: f"{x:.2f}%")
        display_df['RS_Ratio'] = display_df['RS_Ratio'].map(lambda x: f"{x:.4f}")
        display_df['RS_Score_Pct'] = display_df['RS_Score_Pct'].map(lambda x: f"{x:.2f}%")
        display_df['RS_Percentile'] = display_df['RS_Percentile'].map(lambda x: f"{x}")
        
        print(display_df.to_string(index=False))
    
    print("="*80 + "\n")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def run_scanner() -> pd.DataFrame:
    """
    Main scanner execution function.
    
    Returns:
        Results DataFrame
    """
    logger.info("="*80)
    logger.info("STARTING NSE STOCK SCANNER")
    logger.info("="*80)
    
    start_time = time.time()
    
    try:
        # Load universe
        tickers = load_universe()
        
        # Download benchmark
        benchmark_close = download_benchmark_data()
        
        # Download stock data
        stock_data, failed_tickers, skipped_tickers = download_stock_data(tickers)
        
        # Scan stocks
        results_df, rs_percentile_series = scan_stocks(stock_data, benchmark_close)
        
        # Save results
        if not results_df.empty:
            csv_path, excel_path = save_results(results_df)
        
        # Print summary
        print_summary(results_df, len(stock_data), skipped_tickers, failed_tickers)
        
        elapsed = time.time() - start_time
        logger.info(f"Scanner completed in {elapsed:.2f} seconds")
        
        return results_df
        
    except Exception as e:
        logger.error(f"Scanner failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    results = run_scanner()
