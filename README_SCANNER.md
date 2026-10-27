# NSE Stock Scanner

A comprehensive stock scanner for Indian equities (NSE) that applies technical analysis criteria and ranks stocks by relative strength.

## Features

- **Technical Criteria**: EMA50, EMA150, 52-week high proximity
- **Relative Strength**: RS score and percentile ranking vs Nifty 500
- **Batch Processing**: Downloads data efficiently with retry logic
- **Multiple Outputs**: CSV, Excel, and console display
- **Configurable**: All parameters at the top of the script
- **Robust**: Handles missing data, delisted stocks, and rate limits

## Installation

1. Install Python 3.8 or higher

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

All configuration parameters are at the top of `backend/scanner/scanner_v2.py`:

### File Paths
- `UNIVERSE_FILE`: Path to universe Excel file (default: "backend/data/universe.xlsx")
- `UNIVERSE_COLUMN`: Column name containing NSE symbols (default: "Symbol")
- `OUTPUT_DIR`: Directory for output files (default: "backend/data/scanner_output")

### Technical Parameters
- `EMA_FAST`: Fast EMA period (default: 50)
- `EMA_SLOW`: Slow EMA period (default: 150)
- `HIGH_LOOKBACK`: Trading days for 52-week high (default: 260)
- `HIGH_THRESHOLD`: Minimum % of 52-week high (default: 0.70 = 70%)
- `RS_LOOKBACK`: Trading days for RS score (default: 126)
- `MIN_BARS`: Minimum bars required (default: 260)

### Benchmark
- `BENCHMARK_TICKER`: Benchmark ticker (default: "^CRSLDX" = Nifty 500)

### Download Settings
- `CALENDAR_DAYS`: Calendar days to download (default: 800)
- `BATCH_SIZE`: Stocks per download batch (default: 50)
- `SLEEP_BETWEEN_BATCHES`: Seconds between batches (default: 1)

## Usage

### Command Line

Run the scanner:
```bash
python backend/scanner/scanner_v2.py
```

The scanner will:
1. Load the universe from the Excel file
2. Download price data from Yahoo Finance
3. Apply technical criteria
4. Calculate RS scores and percentiles
5. Save results to CSV and Excel
6. Display top 25 results in console

### Output Files

Results are saved to `backend/data/scanner_output/`:
- `scan_results_YYYY-MM-DD.csv`
- `scan_results_YYYY-MM-DD.xlsx`

### Output Columns

- **Rank**: Rank by RS score (1 = strongest)
- **Symbol**: NSE symbol
- **Close**: Latest closing price
- **EMA50**: 50-day EMA
- **EMA150**: 150-day EMA
- **52W_High**: 52-week high
- **Pct_Below_52W_High**: % below 52-week high
- **Close_vs_EMA50_Pct**: % above/below EMA50
- **RS_Ratio**: Relative strength ratio vs Nifty 500
- **RS_Score_Pct**: RS score in % (change over RS_LOOKBACK days)
- **RS_Percentile**: RS percentile (1-99) vs entire universe

## Scan Criteria (All Must Be True)

1. **Close >= EMA50**: Stock is above its 50-day EMA
2. **Close >= 0.70 × 52W High**: Stock is within 30% of its 52-week high
3. **EMA50 >= EMA150**: 50-day EMA is above 150-day EMA (uptrend)

## Universe File Format

The universe file should be an Excel file (.xlsx) with a column containing NSE symbols:

| Symbol | Company Name | Industry |
|--------|--------------|----------|
| RELIANCE | Reliance Industries Ltd | Energy |
| TCS | Tata Consultancy Services | IT |
| HDFCBANK | HDFC Bank Ltd | Banking |

The column name is configurable via `UNIVERSE_COLUMN` parameter.

## Streamlit Frontend (Optional)

Run the Streamlit app:
```bash
streamlit run backend/scanner/app.py
```

This provides a web interface to:
- View scan results
- Re-run the scan
- Filter and sort results
- Export data

## Troubleshooting

### "No data returned for benchmark"
- Check your internet connection
- Verify the benchmark ticker is correct
- Try running during market hours

### "Skipped: insufficient data"
- Some stocks may not have enough historical data
- Increase `CALENDAR_DAYS` parameter
- Check if the stock is recently listed

### Download errors
- Yahoo Finance may rate limit requests
- Increase `SLEEP_BETWEEN_BATCHES` parameter
- Reduce `BATCH_SIZE` parameter

### No stocks pass criteria
- Criteria are strict by design
- Adjust `HIGH_THRESHOLD` or other parameters
- Check if market conditions have changed

## Performance

- **Universe size**: 500-800 stocks
- **Scan time**: 5-15 minutes (depends on internet speed)
- **Data downloaded**: ~800 days per stock
- **Memory usage**: ~500MB-1GB

## Logging

Logs are written to `scanner.log` in the current directory. Check this file for detailed information about:
- Download progress
- Skipped stocks (with reasons)
- Errors and warnings
- Scan statistics

## Notes

- Uses `auto_adjust=True` for split and dividend adjustments
- Drops incomplete current-day candle if market is still open (before 3:30 PM IST)
- Handles missing or delisted tickers gracefully
- RS percentile is calculated against the entire universe before filters

## License

This project is part of the TradingAutomation system.

## Support

For issues or questions, check the logs and verify your configuration parameters.
