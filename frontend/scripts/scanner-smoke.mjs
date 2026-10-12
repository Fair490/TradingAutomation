/**
 * Scanner page behaviour test.
 *
 * Renders the built app in jsdom against a scripted API and drives the Scanner
 * tab through the cases that used to break it:
 *
 *   1. successful scan with matches  -> table, count and diagnostics render
 *   2. valid scan with zero matches  -> explained empty state, no error banner
 *   3. HTTP 503 with a structured    -> error banner with the backend message
 *      scanner error                     (never a silent "no stocks found")
 *   4. malformed JSON                -> "not valid JSON" error banner
 *   5. missing results payload       -> shape-mismatch error banner
 *   6. network failure               -> "Backend unreachable" banner
 *
 *   npm run smoke:scanner            # builds first, then runs this
 *
 * Exits non-zero if any case renders the wrong thing or logs an error.
 */

import { JSDOM } from "jsdom";
import fs from "node:fs";
import path from "node:path";

const dist = "dist";

const html = fs.readFileSync(path.join(dist, "index.html"), "utf8");
const dom = new JSDOM(html, {
  url: "http://localhost:5173/",
  pretendToBeVisual: true,
  runScripts: "outside-only",
});
const { window } = dom;

for (const key of [
  "window",
  "document",
  "HTMLElement",
  "Element",
  "Node",
  "SVGElement",
  "getComputedStyle",
  "localStorage",
  "MutationObserver",
  "Event",
  "CustomEvent",
  "DOMParser",
  "AbortController",
  "AbortSignal",
]) {
  try {
    globalThis[key] = window[key];
  } catch {
    /* read-only global */
  }
}
globalThis.window = window;
globalThis.document = window.document;
try {
  Object.defineProperty(globalThis, "navigator", {
    value: window.navigator,
    configurable: true,
  });
} catch {
  /* node >= 21 exposes a read-only navigator */
}
window.matchMedia = globalThis.matchMedia = () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
});

class SizedResizeObserver {
  constructor(callback) {
    this.callback = callback;
  }
  observe(element) {
    const contentRect = { width: 960, height: 340, top: 0, left: 0 };
    element.getBoundingClientRect = () => ({ ...contentRect, bottom: 340, right: 960 });
    setTimeout(() => this.callback([{ target: element, contentRect }], this), 0);
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = window.ResizeObserver = SizedResizeObserver;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);

// ------------------------------------------------------------------------- //
// A scripted API: the app shell endpoints answer normally, /api/scanner/scan
// answers with whatever the current scenario dictates.
// ------------------------------------------------------------------------- //
const errors = [];
const originalError = console.error;
console.error = (...args) => {
  errors.push(`console.error: ${args.map(String).join(" ").slice(0, 300)}`);
  originalError(...args);
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const shell = {
  "/api/meta": {
    last_updated: null,
    last_computed: null,
    index_name: "Nifty 500",
    index_ticker: "^CRSLDX",
    index_note: null,
    demo_data: false,
    has_data: true,
    n_prices: 1000,
    n_tickers: 3,
    n_stocks: 2,
    universe_count: 2,
    universe_file: "universe.csv",
    first_date: "2024-01-01",
    last_date: "2024-06-28",
    ranges: ["1M", "3M", "6M", "1Y", "3Y", "5Y"],
  },
  "/api/status": { tickers: [], n_ok: 0, n_problem: 0 },
  "/api/breadth": {
    points: [],
    index: [],
    index_name: "Nifty 500",
    latest: null,
    thresholds: { overbought: 80, midline: 50, oversold: 20 },
    footnote: "",
  },
  "/api/advance-decline": {
    points: [],
    index: [],
    index_name: "Nifty 500",
    smoothing_window: 10,
    latest_daily_ratio: null,
    latest_avg_ratio: null,
    divergence: false,
    footnote: "",
  },
  "/api/global": [],
  "/api/global-chart": { series: [] },
  "/api/rs-benchmark": { ticker: "^CRSLDX", name: "Nifty 500", points: [], range: "5Y" },
  "/api/etfs": {
    etfs: [],
    groups: [],
    benchmark_name: "Nifty 500",
    benchmark_change_pct: null,
    range: "5Y",
  },
  "/api/etfs/compare": { series: [], benchmark: null, benchmark_name: "Nifty 500", range: "5Y" },
  "/api/macro": { series: [] },
  "/api/commodities": { series: [] },
  "/api/refresh/status": {
    running: false,
    progress: 0,
    message: "",
    started_at: null,
    finished_at: null,
    ok: null,
    summary: null,
    rows_added: 0,
    tickers_updated: 0,
    failures: [],
    error: null,
  },
};

let scenario = { kind: "ok" };
const scanCalls = { count: 0 };

globalThis.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : input.url;
  const pathname = url.startsWith("http") ? new URL(url).pathname : url.split("?")[0];

  if (pathname === "/api/scanner/scan") {
    scanCalls.count += 1;
    switch (scenario.kind) {
      case "ok":
        return json(scenario.body);
      case "http-error":
        return json(scenario.body, scenario.status);
      case "malformed":
        return new Response("{not json at all", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      case "bad-shape":
        return json({ unexpected: true });
      case "network":
        throw new TypeError("fetch failed");
      default:
        return json(shell["/api/meta"]);
    }
  }

  for (const [prefix, body] of Object.entries(shell)) {
    if (pathname === prefix) return json(body);
  }
  return json({});
};

const entry = fs
  .readdirSync(path.join(dist, "assets"))
  .find((file) => file.endsWith(".js"));
await import(path.resolve(dist, "assets", entry));

const root = window.document.getElementById("root");
const sleep = async (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const baseDiagnostics = {
  universe_size: 756,
  symbols_with_data: 756,
  symbols_evaluated: 750,
  symbols_matched: 3,
  symbols_skipped: 6,
  skipped: { insufficient_history: 6 },
  skipped_symbols: [{ ticker: "NEW.NS", symbol: "NEW", reason: "insufficient_history" }],
  criterion_pass_counts: {
    close_vs_high: 300,
    above_sma50: 280,
    sma50_above_sma150: 260,
    rising_sma200: 250,
    rs_at_high: 30,
  },
  criterion_active: {
    close_vs_high: true,
    above_sma50: true,
    sma50_above_sma150: true,
    rising_sma200: true,
    rs_at_high: true,
  },
  benchmark: "^CRSLDX",
  benchmark_name: "Nifty 500",
  benchmark_first_date: "2021-06-01",
  benchmark_last_date: "2026-10-09",
  benchmark_sessions: 1399,
  evaluation_date: "2026-10-09",
  required_sessions: 252,
  lookback_days: 252,
  price_column: "close",
  invalid_price_rows: 0,
  symbols_with_invalid_prices: 0,
  timings_ms: { data_load: 505.6, indicators: 204.9, total: 1188.4 },
  warnings: [],
  explanation: "3 of 750 evaluated symbols passed all 5 active criteria.",
};

const okBody = {
  results: [
    {
      symbol: "GOOD",
      name: "Good Ltd.",
      ticker: "GOOD.NS",
      close: 123.45,
      close_vs_high_252: 100.0,
      sma50: 110.0,
      sma150: 100.0,
      sma200: 95.0,
      rs: 12.5,
      rising_rs: true,
      passes_close_vs_high: true,
      passes_above_sma50: true,
      passes_sma50_above_sma150: true,
      passes_rising_sma200: true,
      passes_rs_at_high: true,
    },
    {
      symbol: "NULLS",
      name: "Nulls Ltd.",
      ticker: "NULLS.NS",
      close: 50.0,
      close_vs_high_252: null,
      sma50: null,
      sma150: null,
      sma200: null,
      rs: null,
      rising_rs: false,
      passes_close_vs_high: true,
      passes_above_sma50: false,
      passes_sma50_above_sma150: false,
      passes_rising_sma200: false,
      passes_rs_at_high: false,
    },
  ],
  count: 2,
  benchmark: "^CRSLDX",
  criteria: { lookback_days: 252 },
  diagnostics: { ...baseDiagnostics, symbols_matched: 2, symbols_evaluated: 750 },
};

// ------------------------------------------------------------------------- //
// Helpers
// ------------------------------------------------------------------------- //
function tab(label) {
  return [...window.document.querySelectorAll('[role="tab"]')].find((el) =>
    el.textContent?.includes(label),
  );
}

function scanButton() {
  return [...window.document.querySelectorAll("button")].find((el) =>
    /Start Scan|Scan again|Scanning/.test(el.textContent ?? ""),
  );
}

const text = () => root.textContent ?? "";
const hasErrorBanner = () => Boolean(window.document.querySelector('[role="alert"]'));

const failures = [];
function check(name, condition, detail = "") {
  if (!condition) failures.push(`${name}${detail ? ` -> ${detail}` : ""}`);
}

async function runScenario(name, setup, assertions) {
  scenario = setup;
  const before = scanCalls.count;

  // return to the scanner tab (results are page-local state, so re-render it)
  tab("Market Health")?.click();
  await sleep(120);
  tab("Scanner")?.click();
  await sleep(150);

  const button = scanButton();
  if (!button) {
    failures.push(`${name}: could not find the Start Scan button`);
    return;
  }
  button.click();
  await sleep(400);

  check(`${name}: exactly one scan request`, scanCalls.count === before + 1, `calls=${scanCalls.count - before}`);
  assertions();
}

// ------------------------------------------------------------------------- //
// 0. Navigate to the Scanner page
// ------------------------------------------------------------------------- //
await sleep(300);
tab("Scanner")?.click();
await sleep(250);
check("scanner page renders", text().includes("Stock Scanner"));
check("criteria panel renders", text().includes("Scan Criteria"));

// ------------------------------------------------------------------------- //
// 1. Successful scan
// ------------------------------------------------------------------------- //
await runScenario("success", { kind: "ok", body: okBody }, () => {
  check("success: result count shown", text().includes("Scan Results (2 stocks)"), text().slice(0, 200));
  check("success: symbol rendered", text().includes("GOOD"));
  check("success: null metrics render as an em dash", text().includes("—"));
  check("success: diagnostics rendered", text().includes("Scan Diagnostics"));
  check("success: evaluated count shown", text().includes("750"));
  check("success: skipped symbols surfaced", text().includes("Skipped symbols"));
  check("success: no error banner", !hasErrorBanner());
  check("success: explanation shown", text().includes("3 of 750 evaluated symbols"));
});

// ------------------------------------------------------------------------- //
// 2. Valid scan with zero matches
// ------------------------------------------------------------------------- //
await runScenario(
  "empty",
  {
    kind: "ok",
    body: {
      results: [],
      count: 0,
      benchmark: "^CRSLDX",
      criteria: {},
      diagnostics: {
        ...baseDiagnostics,
        symbols_matched: 0,
        explanation:
          "0 of 750 evaluated symbols passed all active criteria. The most restrictive filter was 'RS at lookback high' (12 of 750 passed).",
      },
    },
  },
  () => {
    check("empty: explained empty state", text().includes("No stocks matched"));
    check("empty: explanation rendered", text().includes("most restrictive filter"));
    check("empty: no error banner (zero matches is not an error)", !hasErrorBanner());
    check("empty: no fabricated rows", !text().includes("GOOD"));
  },
);

// ------------------------------------------------------------------------- //
// 3. HTTP 503 with a structured error
// ------------------------------------------------------------------------- //
await runScenario(
  "http-error",
  {
    kind: "http-error",
    status: 503,
    body: {
      detail: {
        code: "benchmark_unavailable",
        message:
          "The benchmark '^CRSLDX' has no stored price history. Run a data refresh before scanning.",
      },
    },
  },
  () => {
    check("503: error banner visible", hasErrorBanner());
    check("503: status shown", text().includes("HTTP 503"));
    check("503: backend message shown", text().includes("no stored price history"));
    check("503: error code shown", text().includes("benchmark_unavailable"));
    check("503: not reported as zero matches", !text().includes("No stocks matched"));
  },
);

// ------------------------------------------------------------------------- //
// 4. Malformed JSON
// ------------------------------------------------------------------------- //
await runScenario("malformed-json", { kind: "malformed" }, () => {
  check("malformed: error banner visible", hasErrorBanner());
  check("malformed: explains invalid JSON", text().includes("not valid JSON"));
  check("malformed: not reported as zero matches", !text().includes("No stocks matched"));
});

// ------------------------------------------------------------------------- //
// 5. Wrong shape (missing results payload)
// ------------------------------------------------------------------------- //
await runScenario("bad-shape", { kind: "bad-shape" }, () => {
  check("bad-shape: error banner visible", hasErrorBanner());
  check("bad-shape: explains the shape mismatch", text().includes("expected results payload"));
  check("bad-shape: did not crash the page", text().includes("Stock Scanner"));
});

// ------------------------------------------------------------------------- //
// 6. Network failure
// ------------------------------------------------------------------------- //
await runScenario("network", { kind: "network" }, () => {
  check("network: error banner visible", hasErrorBanner());
  check("network: explains the backend is unreachable", text().includes("Backend unreachable"));
  check("network: not reported as zero matches", !text().includes("No stocks matched"));
});

// ------------------------------------------------------------------------- //
// 7. Duplicate submissions are prevented
// ------------------------------------------------------------------------- //
scenario = { kind: "ok", body: okBody };
tab("Market Health")?.click();
await sleep(120);
tab("Scanner")?.click();
await sleep(150);
const before = scanCalls.count;
const button = scanButton();
button.click();
button.click();
button.click();
await sleep(500);
check(
  "duplicate clicks trigger a single request",
  scanCalls.count === before + 1,
  `calls=${scanCalls.count - before}`,
);

// ------------------------------------------------------------------------- //
// Report
// ------------------------------------------------------------------------- //
const unexpectedErrors = errors.filter(
  (entry) => !entry.includes("Scanner request failed"),
);
if (unexpectedErrors.length) {
  failures.push(`console errors: ${unexpectedErrors.join(" | ")}`);
}

console.log(`API calls        : ${scanCalls.count} scan request(s)`);
console.log(`Cases checked    : success, empty, http-error, malformed, bad-shape, network, duplicates`);
console.log(`Result           : ${failures.length ? `${failures.length} failure(s)` : "all checks passed"}`);
for (const failure of failures) console.log(`  - ${failure}`);

process.exit(failures.length ? 1 : 0);
