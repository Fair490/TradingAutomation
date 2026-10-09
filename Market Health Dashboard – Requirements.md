# Market Health Dashboard – Requirements

*Hand-off specification for the AI builder. Part 1 of a positional-trading system (O'Neil / Minervini / Weinstein approach).*

## 1. Purpose

A single, clean, local dashboard that shows at a glance how the Indian market and the global backdrop are behaving today, using market breadth, global indices and macro/commodity trends. It must be neat and easy to read, with no clutter.

## 2. Tech stack

- Python, Streamlit (UI), Plotly (interactive charts), DuckDB (storage), yfinance (data), pandas.
- Same stack as the planned backtester so both can share one DuckDB database later.
- Runs locally. One command to launch: `streamlit run app.py`.
- Project structure: `app.py` (UI), `data/` (DuckDB file), `config.py` (tickers, windows, thresholds), `loaders/` (download + update logic), `compute/` (breadth calculations).

## 3. Data requirements

### 3.1 Stock universe

- The user will provide a file (CSV/Excel) with the **current Nifty Total Market constituents**. Read it from `data/universe.csv`.
- Map each symbol to its yfinance ticker (append `.NS`). Allow an optional override column for tickers that differ.
- Only current constituents are used (no historical membership). Show a small footnote on the breadth panels: *"Based on current constituents; survivorship bias applies."*
- Stocks with a short history (recent listings) are included only for dates on which they have data. Breadth percentages use the count of stocks with valid data on that day as the denominator.

### 3.2 Index line for overlays

- Preferred: Nifty Total Market index. If yfinance does not provide it, fall back to **Nifty 500 (`^CRSLDX`)**. Keep the ticker as a single setting in `config.py` and display the name actually used on the chart legend.

### 3.3 Other series (yfinance tickers, confirm availability at build time)

| Panel | Series | Suggested ticker |
| --- | --- | --- |
| Global | Dow Jones | `^DJI` |
| Global | Nasdaq | `^IXIC` |
| Global | Japan (Nikkei 225) | `^N225` |
| Global | Korea (KOSPI) | `^KS11` |
| Global | Hang Seng | `^HSI` |
| Macro | INR/USD | `INR=X` (USD/INR rate) |
| Macro | Dollar Index | `DX-Y.NYB` |
| Macro | US 10-Year yield | `^TNX` |
| Commodities | Gold | `GC=F` |
| Commodities | Silver | `SI=F` |
| Commodities | UK Oil (Brent) | `BZ=F` |

Note: `INR=X` quotes how many rupees per one US dollar, so a rising line means a weaker rupee. Label the chart clearly ("USD/INR – rising = weaker INR").

### 3.4 History and storage

- First run: download **5 years of daily data** for all tickers, store adjusted close (and close) per symbol in DuckDB.
- Subsequent refreshes: fetch only the missing dates after the last stored date for each ticker and append. Never re-download everything unless the user chooses "Full rebuild".
- Download in batches (e.g. 50 tickers at a time) with retries. Log any ticker that fails or returns no data; show failures in a small "Data status" expander.
- The 200-day moving average needs 200 prior days, so the initial download for the stock universe must start about **14 months before** the 5-year window so that the 200DMA is valid from day one of the chart.
- Store computed series (A/D, breadth) in their own tables so the UI loads instantly.

## 4. Calculations

### 4.1 Advance/Decline

- For each trading day: **Advance** = stock close > previous close; **Decline** = close < previous close; unchanged is ignored.
- **A/D Ratio** = advances ÷ declines.
- **A/D Line** = cumulative sum of (advances − declines).
- Provide an optional **10-day smoothing** of the ratio (toggle).

### 4.2 Market breadth (200DMA)

- For each stock and date: compute the 200-day simple moving average of close.
- **% of stocks above 200DMA** = stocks with close > 200DMA ÷ stocks with valid 200DMA × 100. This is the main line on the chart.
- Also compute the **Above/Below ratio** (count above ÷ count below) and make it available as a switch ("Show: % above | Above/Below ratio").
- Reference lines on the % chart: **80% (overbought zone), 50% (midline), 20% (oversold zone)**. Configurable in `config.py`.
- Show today's reading as a large number with the change vs previous day and vs 1 week ago.

## 5. Dashboard layout and panels

One page, top to bottom, with a light, minimal theme, generous spacing, consistent colours and short plain-English titles. Use sections with clear headers rather than many tabs.

### Header bar

- Title, "Last updated: date/time", and a **Refresh Data** button.
- Date range buttons: **1M, 6M, 1Y, 3Y, 5Y** (default 5Y). Applies to all long-term charts.

### Panel 1 – Advance/Decline

- Line chart of the A/D ratio (with optional 10-day smoothing) for 5 years.
- Switch: Ratio | A/D Line.
- **Toggle: "Show Nifty Total line"** (secondary right-hand axis, default on).

### Panel 2 – Market Breadth (stocks above 200DMA)

- Line chart of % of stocks above 200DMA, with 80/50/20 reference lines, for 5 years.
- **Toggle: "Show Nifty Total line"** (secondary right-hand axis, default on).
- Headline number for today beside the chart.

### Panel 3 – Global Markets Today

- Five small cards (Dow, Nasdaq, Nikkei, KOSPI, Hang Seng), each showing last close, % change for the last session (green/red), and a compact 1-month line chart.
- Show each market's last trading date so that different time zones and holidays are clear.
- No intraday charts.

### Panel 4 – Currency, Dollar and Bond Yield

- Three line charts for 5 years: USD/INR, Dollar Index, US 10-Year yield.
- Toggle: **Normalised view** (rebased to 100 at the start of the selected range) so the lines can be compared on one chart. Default is separate charts.

### Panel 5 – Commodities

- Gold, Silver and Brent (UK Oil) for 5 years.
- Same **Normalised view** toggle as Panel 4.

### Common chart behaviour

- Interactive (hover values, zoom, pan, unified hover tooltip), consistent date axis across panels.
- Tooltips show date and value. Colours stay consistent: Nifty line always grey, the main series always the panel's accent colour.
- Charts must fit common laptop widths; no horizontal scrolling.

## 6. Refresh behaviour

- Manual **Refresh Data** button only (no scheduler in version 1).
- On click: show a progress bar, fetch missing days, recompute A/D and breadth for new dates only, update the "Last updated" stamp, and show a summary ("212 days added" / "3 tickers failed").
- If the market was closed or no new data exists, say so instead of showing an error.
- A "Full rebuild" option sits in an advanced expander.

## 7. Non-functional requirements

- Page load under about 3 seconds after the first run (read computed tables from DuckDB, not recalculating).
- Full initial download may take several minutes; show progress.
- Handle yfinance rate limits and gaps gracefully (retry with back-off, forward-fill only for holiday gaps in macro series, never for stock prices).
- Clean, commented code with a README covering setup, the universe file format and troubleshooting.

## 8. Out of scope for version 1

- Intraday data, automated scheduling, alerts, historical constituent changes, and any "market Healthy / Weak" summary label.
- Later extensions: new highs vs new lows, stocks above 50DMA, Minervini trend-template count, and hooking the dashboard's regime reading into the backtester's position-sizing module.

## 9. Acceptance checklist

- [ ] Universe file loads and unmapped or failed tickers are listed
- [ ] 5 years of daily data stored for all stocks, index and macro series
- [ ] A/D ratio and A/D line chart with Nifty toggle works
- [ ] % above 200DMA chart with 80/50/20 lines and Nifty toggle works
- [ ] Five global index cards show last session % change and 1M chart
- [ ] USD/INR, Dollar Index, US 10Y charts render, normalised toggle works
- [ ] Gold, Silver, Brent charts render, normalised toggle works
- [ ] Refresh button appends only new days and reports results
- [ ] Layout is clean, consistent and readable on a laptop screen
