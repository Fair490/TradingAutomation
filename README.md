# Market Health Dashboard

A local, two-part dashboard showing how the Indian market and the global backdrop
are behaving today: market breadth, advance/decline, global indices, macro and
commodities. Part 1 of a positional-trading system (O'Neil / Minervini /
Weinstein style). Spec:
[`Market Health Dashboard – Requirements.md`](Market%20Health%20Dashboard%20–%20Requirements.md).

```
backend/    FastAPI + DuckDB + yfinance   ->  http://127.0.0.1:8000
frontend/   React + Vite + Tailwind       ->  http://localhost:5173
```

The browser only ever talks to the Vite dev server, which proxies `/api` to the
backend — so there is no CORS setup and no hard-coded URL anywhere in the UI.

---

## 1. Quick start

### Backend (terminal 1)

```powershell
# from the repository root, first time only
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# every time
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

macOS / Linux equivalent:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
./.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

Interactive API docs: <http://127.0.0.1:8000/docs>

### Frontend (terminal 2)

```bash
cd frontend
npm install     # first time only
npm run dev
```

Open <http://localhost:5173> and press **Refresh data**. The first download
fetches 5 years + a 14-month warm-up of daily closes for every symbol in the
universe plus the index, global, macro and commodity series — a few minutes,
with a live progress bar. Every refresh after that is incremental and takes
seconds.

### Preview the UI without downloading anything

```bash
./.venv/bin/python backend/scripts/seed_demo_data.py          # synthetic prices
./.venv/bin/python backend/scripts/seed_demo_data.py --clear  # wipe them again
```

A warning banner is shown whenever demo data is loaded.

---

## 2. Project layout

```
backend/
  main.py                FastAPI app (uvicorn entry point: backend.main:app)
  config.py              Tickers, windows, thresholds — the only place to tweak
  api/
    routes.py            All /api endpoints
    schemas.py           Pydantic response models (the frontend contract)
    refresh_job.py       Background download job + progress state
  loaders/
    universe.py          Reads data/universe.csv, maps symbols to Yahoo tickers
    prices.py            yfinance downloads: batching, retries, incremental update
    store.py             DuckDB schema, one shared connection, helpers
  compute/
    breadth.py           A/D and % above 200DMA (DuckDB window functions)
    series.py            Ranges, normalisation, last-session snapshots
  scripts/
    seed_demo_data.py    Offline synthetic data for previews
  tests/                 25 pytest cases (maths, loaders, HTTP API) — no network
  data/
    universe.csv         >>> YOUR STOCK LIST <<<  (the only universe source)
    market.duckdb        Created on first run; gitignored

frontend/
  src/
    App.tsx              Page composition, banners, theme
    components/          TopBar, BreadthPanel, AdvanceDeclinePanel,
                         GlobalPanel, SeriesPanel, StatusPanel, ui, charts
    lib/                 Typed API client, formatting, refresh polling hook
  vite.config.ts         Dev server + /api proxy to 127.0.0.1:8000
  scripts/smoke.mjs      Headless render check (`npm run smoke`)
```

---

## 3. The stock universe

**`backend/data/universe.csv` is the single source of truth.** Nothing else is
used — no hard-coded ticker list, no other file.

The standard NSE constituents export works unchanged:

| Column | Required | Notes |
| --- | --- | --- |
| `Symbol` | yes | NSE symbol, e.g. `RELIANCE` (a single-column file of symbols also works) |
| `Company Name` | no | shown in Data status |
| `Industry` | no | kept for later use |
| `Series` | no | rows outside `config.UNIVERSE_SERIES_KEEP` (`EQ`, `BE`, `RR`, …) are skipped |
| `Yahoo Ticker` | no | override when Yahoo's ticker is not `<SYMBOL>.NS` |

Mapping rule: `RELIANCE` → `RELIANCE.NS`. To swap universes, replace the file
and press **Refresh data**: new symbols are downloaded with full history and
symbols that are no longer listed are dropped from the database.

Only current constituents are used, so every breadth panel carries the
footnote *"Based on current constituents; survivorship bias applies."*

### ETFs

The ETF panel is **not** driven by `universe.csv` — it is a fixed, editable
list in `backend/config.py → ETF_SERIES`, a tuple of
`(NSE symbol, display label, group)` per fund:

```python
("BANKBEES", "Nifty Bank", "Banking"),
```

Symbols map to Yahoo the same way (`BANKBEES` → `BANKBEES.NS`). Add, remove or
rename rows there and press **Refresh data**; no other file needs touching.
The groups listed in the file become the filter chips in the UI.

---

## 4. Data source and storage

- **Yahoo Finance via `yfinance`** — daily closes only, no intraday.
- Downloads run in batches of 50 (`config.BATCH_SIZE`) with three retries and
  exponential back-off. A failing batch never aborts the run; failures are
  recorded per ticker and listed under **Data status**.
- Everything lands in one DuckDB file, `backend/data/market.duckdb`
  (tables: `prices`, `tickers`, `advance_decline`, `breadth_200dma`, `meta`),
  which the planned backtester can attach to later.
- Refreshes ask each ticker only for the days after its stored maximum date
  (re-fetching the final bar so a partial day gets corrected), then recompute
  only the new dates. The A/D line continues from the last stored value.
- Holiday gaps may be forward-filled for macro/commodity display.
  **Stock prices are never forward-filled.**

### Which index is the grey overlay?

Yahoo does not reliably publish the Nifty Total Market index, so
`config.INDEX_CANDIDATES` is tried in order and the first ticker that returns
data wins — in practice the documented fallback **Nifty 500 (`^CRSLDX`)**. The
name actually used is stored and shown in every legend and in Data status.

---

## 5. What is calculated

**Advance / Decline** — advance = close above the previous close, decline =
below, unchanged ignored. Ratio = advances ÷ declines; the A/D line is the
cumulative sum of (advances − declines); optional 10-day smoothing of the ratio.

**Breadth (% above 200DMA)** — 200-day simple moving average per stock;
`% above = stocks above their 200DMA ÷ stocks with a valid 200DMA × 100`.
Recent listings are excluded until they have 200 observations, so the
denominator moves with the data. Reference bands at 80 / 50 / 20.

Both are computed with DuckDB window functions over ~1.2M rows in well under a
second and stored, so the UI only ever reads precomputed tables.

**Scanner** — screens every symbol in the universe file against the trend
template below. All windows are *trading sessions*, not calendar days, and the
benchmark is forward-filled onto each stock's own sessions:

| Rule | Default | Toggle |
| --- | --- | --- |
| `close ≥ min_close_vs_high × max(close, lookback)` | 80% of the 252-session high | threshold |
| `close ≥ SMA(50)` | — | `require_above_sma50` |
| `SMA(50) ≥ SMA(150)` | — | `require_sma50_above_sma150` |
| `SMA(200)[t] > SMA(200)[t-20 sessions]` | — | `require_rising_sma200` |
| `RS[t] ≥ max(RS, lookback)` where `RS = close ÷ benchmark × 100` | 252 sessions | `require_rs_at_high` |

A rule whose window extends past the available history simply does not pass.
Symbols with no prices, fewer sessions than the enabled rules need, or a last
bar more than 10 sessions old are *skipped and reported* (they are never
silently treated as "no match"). A scan reads the whole universe in one query
and computes every indicator once across a dates × tickers matrix, so it takes
about a second for a 750-symbol universe and does not hold the database lock -
`/api/meta`, `/api/breadth` and `/api/advance-decline` stay responsive while it
runs.

---

## 6. API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/meta` | Freshness, index in use, row counts, universe size |
| GET | `/api/breadth?range=5Y` | Breadth series + index overlay + today's reading |
| GET | `/api/advance-decline?range=5Y` | A/D ratio, 10-day average, divergence flag, A/D line, overlay |
| GET | `/api/global` | Seven global cards (Dow, Nasdaq, Nikkei, KOSPI, Hang Seng, S&P 500, India VIX) with daily change, 1M spark, 1M/1Y/5Y changes, display unit, stale flag and 50/150 MA |
| GET | `/api/macro?range=5Y` | USD/INR, Dollar Index, US 10Y (in bps) with 1M/1Y/5Y changes, unit, MA overlays |
| GET | `/api/commodities?range=5Y` | Gold, Silver, Brent with units, period changes, MA overlays |
| GET | `/api/etfs?range=1Y` | ETF leaderboard: headline + per-period (1M/3M/6M/1Y) change & relative performance, plus 52w-high, 50-DMA, 150-DMA stats |
| GET | `/api/etfs/compare?symbols=BANKBEES,ITBEES&range=1Y&benchmark=true` | Full lines for up to 8 ETFs plus the index |
| GET | `/api/status` | Per-ticker status, row counts, failures |
| POST | `/api/scanner/scan` | Run the trend-template scan. Body: `benchmark_ticker`, `min_close_vs_high`, the four `require_*` toggles, `lookback_days`. Returns `results`, `count`, `benchmark`, `criteria` **and `diagnostics`** (universe/evaluated/matched/skipped counts, per-criterion pass counts, skipped-symbol reasons, phase timings, warnings, explanation). `400` unknown benchmark/parameters, `409` scan already running, `503` missing market data or universe — a data failure is never returned as an empty result |
| GET | `/api/scanner/scan` | Same scan via query parameters (handy for curl) |
| POST | `/api/refresh` | Start a download (`{"full_rebuild": false}`) |
| GET | `/api/refresh/status` | Progress, message and the final summary |
| GET | `/api/health` | Liveness |

`range` is one of `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`.

---

## 7. The interface

The dashboard is a multi-page React app with a sticky navigation bar across
the top. Six pages:

| Page | Status |
| --- | --- |
| **Market Health** | Current panels (breadth, A/D, global, macro, commodities, status) |
| **Sector Performance** | ETF leaderboard, compare chart, pop-out detail view |
| **Scanner** | Trend-template screen (close vs high, 50/150/200DMA, benchmark RS) with live diagnostics |
| **Portfolio** | _Coming soon_ — holdings, P&L, sector exposure |
| **Terminal** | Debug terminal: live backend logs |
| **Trade Leader** | _Coming soon_ — relative-strength leaders across sectors |

### Market Health page

- **Sticky header** — freshness pill, data-through date, range buttons
  (1M/3M/6M/1Y/3Y/5Y), light/dark toggle, and a Refresh button.
- **Breadth panel** — today's reading with 1-day and 1-week deltas, an
  above/below split bar, the 5-year chart with shaded overbought/oversold
  bands, a legend, and the grey Nifty overlay on a right-hand axis.
- **Advance/Decline panel** — today's advancing-vs-declining bar, the daily
  ratio, the 10-day average ratio, then Ratio or A/D line with the smoothing
  toggle as a clear on/off control. A yellow divergence banner flags when the
  A/D line and the index have moved in opposite directions for the last few
  sessions.
- **Global markets** — seven cards (Dow, Nasdaq, Nikkei, KOSPI, Hang Seng,
  S&P 500, India VIX). Each card shows the daily change in a coloured pill,
  a 1-month sparkline coloured by the trend (green if the 1M change is up,
  red otherwise), the display unit (USD/oz, ₹/$, bps, index), and 1M / 1Y /
  5Y changes. A small amber **stale** badge appears on any card whose last
  close is older than the freshest card (weekend / holiday in that market).
- **Macro and Commodities** — three charts each with a **Daily / Weekly /
  Monthly** switch, optional **50 MA** and **150 MA** overlays, and the
  Normalised toggle. Each chart card shows its 1M / 1Y / 5Y change and the
  display unit.
- **Data status** — searchable ticker table, problems-only filter, and the
  full rebuild behind a confirmation checkbox.

### Sector Performance page

- **28 ETF cards** across six groups: Banking (3), Sector (10), Theme (7),
  Broad market (4), International (2), Commodity (2). Each card shows the
  sparkline, the headline performance vs the benchmark, and a 52-week high /
  50-DMA / 150-DMA footer.
- **Rank by** selector (1M / 3M / 6M / 1Y) sorts the cards by relative
  performance vs the benchmark over the chosen window. ETFs listed after the
  ranking window are flagged with a *"since …"* badge.
- **Click any card** to pop out a full-size chart with the benchmark overlaid.
- **Select up to six cards** (tap the checkbox) to plot them together in a
  rebased comparison chart, with the benchmark as a dashed grey line.

### Other features

- Dark mode, keyboard-reachable controls, skeleton loaders, and no horizontal
  scrolling down to roughly a 1024px laptop width.

---

## 8. Tests

```bash
./.venv/bin/python -m pytest backend/tests -q     # backend suites, no network
cd frontend && npm run typecheck                  # strict TypeScript
cd frontend && npm run smoke                      # headless render check (backend must be up)
cd frontend && npm run smoke:hostile              # same, against deliberately nasty data
cd frontend && npm run smoke:scanner              # scanner page: results, empty, errors, malformed
```

`npm run smoke` renders the built app in jsdom with a ResizeObserver that
reports a real size, so **the charts actually draw** — that is where
data-shape crashes surface. `smoke:hostile` points it at a stub API that
serves the shapes real Yahoo data produces and demo data never does: an
overlay index that returned nothing, a failed series, an all-null series, a
session with zero declines and missing percentage changes.

`smoke:scanner` drives the Scanner tab through seven cases: a successful scan
(matches, diagnostics, null metrics), a legitimate zero-match scan, an HTTP 503
with a structured scanner error, invalid JSON, a missing results payload, a
network failure, and repeated clicks (one request only).

The Python suite covers the A/D counts and cumulative line, incremental
updates, the 200DMA warm-up rule, normalisation, symbol mapping, the real
universe file, yfinance response parsing, every HTTP endpoint, and the scanner:
each filter's boundary, the moving-average / rolling-high / RS maths, benchmark
date alignment, skipped-symbol reporting, every error path (missing benchmark,
universe and database; invalid parameters; injected database and calculation
failures), concurrent scans (409), that `/api/meta` stays responsive during a
scan, that the universe is read in a single query, and a 400-symbol
performance budget.

---

## 9. Troubleshooting

| Symptom | What to do |
| --- | --- |
| `Universe file not found` | Put your list at `backend/data/universe.csv` with a `Symbol` column. |
| Frontend shows "Could not load …" | The backend is not running, or not on port 8000. Start uvicorn first. |
| Many tickers show `empty` | Symbol → Yahoo ticker mismatch. Add a `Yahoo Ticker` column for those rows and refresh. |
| `YFRateLimitError` / lots of failures | Yahoo is throttling. Wait a few minutes and refresh again — only missing days are retried. Raising `REQUEST_PAUSE_SECONDS` or lowering `BATCH_SIZE` in `backend/config.py` also helps. |
| Breadth line starts late | Not enough history for the 200DMA — raise `MA_WARMUP_MONTHS` and do a full rebuild. |
| Database looks wrong | Data status → Full rebuild, or delete `backend/data/market.duckdb` and refresh. |
| Port already in use | Change the port in the uvicorn command and in `frontend/vite.config.ts` (`proxy` target). |
| A panel shows a red "could not be drawn" box | A render error is now contained to that panel instead of blanking the page. The box names the component and shows the message — send me that text. |

---

## 10. Out of scope in version 1

Intraday data, scheduling, alerts, historical constituent changes and any
"Healthy / Weak" summary label. Planned next: new highs vs new lows, stocks
above 50DMA, a Minervini trend-template count, and feeding the regime reading
into the backtester's position sizing.
