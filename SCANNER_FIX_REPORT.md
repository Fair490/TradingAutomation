# Scanner repair report

Branch: `arena/53d2588a-tradingautomation` (commit `d8f4bc9`, based on
`arena/c8b92dd5-tradingautomation` @ `7bfc240`, the branch that actually holds
the application — `main` only contains the README/skeleton).
Pull request: <https://github.com/Fair490/TradingAutomation/pull/1>

Reproduced symptom: `POST /api/scanner/scan` returned 200 but took 618 s, and a
simultaneous `/api/meta` took over 10 minutes. Everything below was measured on
a synthetic DuckDB built to mirror the real one (756 universe symbols × ~1,400
sessions = 1,059,043 price rows, 5 years of daily bars) because this checkout
contains no `backend/data/market.duckdb`. No real data, database or local file
was touched or replaced.

---

## 1. Confirmed root causes

| # | Defect | Where | Evidence |
| --- | --- | --- | --- |
| 1 | `compute_sma` walked every rolling window in pure Python, O(n × window) per call, called **3× per symbol** (50/150/200) | `backend/compute/series.py` | 2,872,800 window evaluations; **232 s of a 259 s scan** (cProfile) |
| 2 | The whole per-symbol loop ran inside one `store.session()` block. `session()` holds the process-wide DuckDB `RLock` for the entire block, so every other endpoint waited for the scan | `backend/scanner/__init__.py`, `backend/loaders/store.py` | `/api/meta` took **234.29 s during a 235 s scan** (vs 0.10 s idle) — the reported "meta also took 10+ minutes" |
| 3 | N+1 query pattern: one `load_series()` per universe member, full 5-year history each, plus per-stock `sort_values`, `reset_index`, `pd.Series` construction and `reindex/ffill` of the benchmark | `backend/scanner/__init__.py` | 757 queries / 2.37 s for the reads alone; benchmark RS rebuilt for every stock |
| 4 | Data failures were returned as success: empty benchmark, empty universe, and empty database all produced `200 {"results": [], "count": 0}` | `backend/scanner/__init__.py` | `if benchmark_df.empty: return pd.DataFrame()` |
| 5 | Silent skips: `if stock_df.empty or len(stock_df) < lookback_days: continue` — no counters, no reasons, no per-criterion statistics, no timings | `backend/scanner/__init__.py` | none of these were reported anywhere |
| 6 | Unvalidated inputs: `benchmark_ticker` accepted anything, `min_close_vs_high`/`lookback_days` unbounded | `backend/scanner/routes.py` | `min_close_vs_high=5.0` was silently accepted |
| 7 | Frontend treated any response as success (`await response.json()` with no `ok`/shape check) and only `console.error`-ed failures; a 500 body crashed rendering | `frontend/src/components/ScannerPage.tsx` | code review; reproduced in the new jsdom test |
| 8 | Rolling highs used `min_periods=1`, so a hole in the data could manufacture a false "at the high" pass | `backend/scanner/__init__.py` | code review |
| 9 | `node_modules` was not ignored by `.gitignore` (a stray `git add .` would have committed the dependency tree) | `.gitignore` | `git status` showed `?? frontend/node_modules/` |

## 2. Files changed and why

| File | Change |
| --- | --- |
| `backend/scanner/engine.py` **(new)** | Vectorised scan engine: single bulk read, one indicator pass over a dates × tickers matrix, per-symbol classification, independent criteria, diagnostics, typed errors, one-scan-at-a-time guard |
| `backend/scanner/__init__.py` | Public API kept (`scan_stocks` still returns a `DataFrame`); now delegates to the engine and raises typed errors instead of returning an empty frame on failure; adds `run_scan`, `ScanSettings`, `scan_slot` |
| `backend/scanner/routes.py` | Request validation, status-code mapping (400/409/422/500/503), structured `{code, message}` error bodies, `diagnostics` in the response, response-serialization timing |
| `backend/loaders/store.py` | `load_price_panel()` (one query for the whole universe), `count_prices()`, `known_ticker_rows()` |
| `backend/compute/series.py` | `compute_sma()` reimplemented with the same semantics on `pandas.rolling` (the O(n × window) trap is gone for any future caller) |
| `backend/config.py` | Scanner section: SMA windows (50/150/200), 20-session 200DMA lookback, lookback bounds, price column, staleness limit, skipped-symbol cap |
| `frontend/src/components/ScannerPage.tsx` | Status + shape validation, visible error banner, timeout/network/malformed handling, duplicate-submit guard, elapsed progress, diagnostics panel, honest empty state, null-safe table/CSV |
| `frontend/src/lib/api.ts` | Scanner contract types (`ScanCriteria`, `ScanResult`, `ScanDiagnostics`, `ScanResponse`, `ApiErrorDetail`) kept in sync with the backend |
| `backend/tests/test_scanner.py` **(new)** | 37 tests (see §5) |
| `frontend/scripts/scanner-smoke.mjs` **(new)** | jsdom behaviour test for the scanner page (success/empty/503/malformed/bad-shape/network/duplicate clicks) |
| `frontend/package.json` | `npm run smoke:scanner` |
| `README.md`, `.gitignore` | Scanner strategy + API documented; `node_modules/` and `*.tsbuildinfo` ignored |

The strategy was **not** changed. The new engine was run head-to-head against
the original implementation on identical data: same 36 matching symbols, and
zero differences across `close`, `close_vs_high_252`, `sma50`, `sma150`,
`sma200`, `rs`, `rising_rs` and all five `passes_*` flags.

## 3. How the calculations and validation were corrected

* **Sessions, not calendar days** — every window is rows in `prices`
  (50/150/200/252/20). Unchanged, now stated explicitly in config and code.
* **Benchmark RS computed once per scan** — `RS = close / benchmark × 100` with
  the benchmark forward-filled onto the panel's date index. This is identical to
  the old per-stock `reindex(...).ffill()` (leading NaNs before the benchmark's
  first date stay NaN; holidays are forward-filled) but is computed once for the
  whole universe. Verified by a dedicated date-alignment test.
* **"20 sessions back" is counted in observations, not rows** — a helper finds
  the *n*-th valid observation from the end per symbol, exactly matching the
  original per-symbol slicing even when a symbol has gaps.
* **Full windows for the rolling highs** (`min_periods = window`) — removes the
  possibility of a false "at the high" pass when history has holes; identical
  results on complete histories.
* **Data hygiene** — non-finite, zero and negative closes are excluded and
  counted (`invalid_price_rows`, `symbols_with_invalid_prices`); duplicate
  `(ticker, date)` rows are collapsed; dates are sorted; `NULL` closes never
  reach the JSON (verified by asserting no `NaN`/`Infinity` tokens in responses).
* **Stale symbols** — a symbol whose last bar is more than 10 sessions behind
  the freshest bar is skipped and reported instead of being judged as a live
  setup; symbols are otherwise still evaluated as of their own last session.
* **Honest skips** — `no_price_history`, `invalid_prices`,
  `insufficient_history`, `stale_data` are counted and the first 100 symbols are
  echoed back with their reason.
* **Adequate history** — a symbol needs `max(lookback, 220)` sessions when the
  rising-200DMA rule is on (a 20-session lookback difference on a 200-session
  average), i.e. the original 252-row gate widened to what the enabled rules
  actually require; short symbols are reported, not silently failed.
* **Price field made explicit** — Yahoo's raw `Close` is already split-adjusted
  (`Adj Close` adds dividends); the whole dashboard uses `Close`, so the scanner
  does too, now via `config.SCANNER_PRICE_COLUMN` (set `adj_close` to switch).
* **Criteria counted independently** before the AND, so "why did nothing match"
  is answerable from the payload (`criterion_pass_counts`, `criterion_active`,
  `explanation` naming the most restrictive filter).

## 4. How the 10-minute runtime and the blocking were addressed

* The hot path (Python window loops) is gone: indicators are computed once with
  vectorised pandas operations over a `(dates × tickers)` matrix.
* The universe is read with **one** joined query instead of 757, and the DuckDB
  lock is now held only for that short read plus two small metadata queries — no
  computation happens inside `store.session()`. Measured worst case for an
  unrelated endpoint during a scan: **249 ms** (the panel read itself), typical
  **12–41 ms**.
* FastAPI runs the route in its thread-pool (it is a `def` endpoint), so the
  event loop is never blocked; because the lock is no longer held, sibling
  requests are no longer queued behind the scan.
* The scan stays a plain synchronous request (~1 s); a background-job queue was
  not justified. Protection against duplicate concurrent scans is a
  non-blocking semaphore that returns **409 `scan_in_progress`**.
* The frontend shows elapsed seconds while scanning and disables/closes the
  submit path, and reports timeouts (120 s) explicitly.

## 5. Tests actually run

| Command | Result |
| --- | --- |
| `./.venv/bin/python -m pytest backend/tests -q` | **75 passed** (38 pre-existing + 37 new) |
| `./.venv/bin/python -m pytest backend/tests/test_scanner.py -q` | **37 passed** in 5.63 s |
| `python -m compileall backend` + import of every module | OK |
| `cd frontend && npx tsc --noEmit` | OK (strict) |
| `cd frontend && npm run build` | OK (`tsc -b && vite build`) |
| `cd frontend && node scripts/scanner-smoke.mjs` (`npm run smoke:scanner`) | **all checks passed** — success, empty, HTTP 503, malformed JSON, bad shape, network failure, duplicate clicks |
| `cd frontend && npm run smoke:hostile` | no errors, all panels/tabs present |
| `cd frontend && npm run smoke` (against a live API on :8000) | no errors, all panels present |

New backend coverage includes: a scan with known matches; a valid zero-match
scan; missing benchmark history; unknown benchmark; benchmark with only invalid
closes; missing/empty universe; empty database; insufficient history; stale
symbols; NaN/zero/negative prices; all-symbols-skipped; each filter's boundary
(inclusive `>=`, strict `>`, missing-history cases); the combined AND; SMA and
rolling-high arithmetic against hand-computed values; RS alignment across
benchmark holidays and a late-starting benchmark; observation-based "n back"
positioning; invalid parameters (422); `ScanSettings.validate()` messages;
injected `duckdb.Error` and injected `RuntimeError`; **a regression test that a
scanner failure is never a successful zero-result scan**; 409 on a concurrent
scan; `/api/meta` staying responsive during a scan; the single-bulk-query
regression; and a 400-symbol performance budget (2.25 s, limit 15 s).

## 6. Before / after (same dataset, same criteria)

| Measurement | Before | After |
| --- | --- | --- |
| Scan, 756 symbols × 1,399 sessions (1.06 M rows) | **249.03 s** | **1.15 s** (216.8× faster) |
| Matching symbols | 36 | 36 (identical set, identical values) |
| `/api/meta` while a scan runs | **234.29 s** | **0.05 s** |
| Warm scans over real HTTP (`uvicorn`, 756 symbols) | n/a | **0.98–1.07 s** (≈3.0 s under 37 parallel requests) |
| `/api/meta` / `/api/breadth` / `/api/advance-decline` during an HTTP scan | blocked for the whole scan | median 39 ms / 12 ms / 12 ms, worst 192 ms / 40 ms / 53 ms |
| Scanner phase timings (reported in the payload) | not measured | universe 38 ms · benchmark 22 ms · data load 506 ms · matrix 412 ms · indicators 205 ms · evaluation 3 ms · serialization 2 ms · **total ≈ 1.19 s** |

The field number (618 s) is higher than the 249 s synthetic baseline because a
real database has more rows and the old code's cost scaled with rows × window;
the fix removes that scaling entirely.

## 7. Remaining defects, limitations and checks not run

* **No real database here** — `backend/data/market.duckdb` is absent in this
  checkout, so all timings come from the synthetic equivalent described above.
  Re-run `POST /api/scanner/scan` against your own database to confirm.
* **The yfinance refresh path was not exercised** (no access to Yahoo Finance in
  this sandbox); `backend/loaders/prices.py` was read but not modified. The
  scanner now surfaces its `tickers.status` reality indirectly through skipped
  reasons, but partial-refresh handling was validated only by seeding partial
  data (missing tickers, short histories, stale last bars, invalid prices).
* **Interior data gaps** — if a symbol is missing sessions *inside* the trailing
  window, the stricter full-window rule can make it fail a filter it previously
  passed (never the other way round). This is deliberate and documented.
* **`rising_rs` display flag** is computed on the panel's session grid rather
  than the symbol's compressed series; identical for symbols trading every
  session, conservative (False) for gappy ones. It is a display flag, not a
  filter.
* **No linter is configured** in this repository (no eslint/ruff/flake8 config,
  no CI workflows), so "lint where configured" = nothing to run; `tsc` and
  `pytest` are the enforced gates.
* **ETF/portfolio pages untouched** — they have the same N+1 read pattern
  (`/api/etfs` calls `load_series` per ETF), which is fine at 28 ETFs and was
  deliberately left alone.
* **No cancellation** for an in-flight scan: it is a ~1 s request, so a cancel
  path is not warranted; the frontend aborts the fetch after 120 s.

## 8. How to pull

The fix is on this session's branch and in PR #1 (opened against your working
branch, so it is a one-commit, fast-forward change):

```bash
# 1) fetch the new branch
git fetch origin

# 2) either check it out directly
git checkout arena/53d2588a-tradingautomation
git pull

# 3) or keep working on your development branch and fast-forward it
git checkout arena/c8b92dd5-tradingautomation
git merge --ff-only origin/arena/53d2588a-tradingautomation
git push origin arena/c8b92dd5-tradingautomation
```

Or merge the PR in the browser:
<https://github.com/Fair490/TradingAutomation/pull/1>

Then, on your machine:

```bash
# backend (Windows PowerShell: .\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000)
./.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# frontend
cd frontend && npm install && npm run dev

# checks
./.venv/bin/python -m pytest backend/tests -q
cd frontend && npm run typecheck && npm run smoke:scanner
```

`frontend/dist`, `frontend/node_modules`, `.venv` and
`frontend/tsconfig.tsbuildinfo` are local build artifacts (now git-ignored);
nothing in `backend/data/` was created, modified or deleted.
