/**
 * Hostile stub API used by the smoke test.
 *
 * It mimics the shapes real Yahoo data produces that synthetic demo data never
 * does: an overlay index that returned nothing, series with no points at all,
 * all-null stretches, missing session changes and a single-point series.
 *
 *   node scripts/stub-api.mjs            # listens on 127.0.0.1:8099
 */

import http from "node:http";

const DAYS = 40;
const dates = Array.from({ length: DAYS }, (_, i) => {
  const d = new Date(Date.UTC(2026, 0, 5 + i));
  return d.toISOString().slice(0, 10);
});

const breadth = {
  // first few days have no valid 200DMA yet -> nulls, like a real first run
  points: dates.map((date, i) => ({
    date,
    pct_above: i < 6 ? null : 40 + Math.sin(i / 4) * 25,
    above_below: i < 6 ? null : 1 + Math.sin(i / 4),
    n_valid: i < 6 ? 0 : 740,
    n_above: i < 6 ? 0 : 400,
    n_below: i < 6 ? 0 : 340,
  })),
  index: [], // <- Yahoo had no data for ^CNXTOTAL / ^CRSLDX
  index_name: "Nifty 500",
  latest: {
    date: dates.at(-1),
    pct_above: 54.3,
    above_below: null,
    n_above: 402,
    n_below: 338,
    n_valid: 740,
    change_1d: null,
    change_1w: 3.2,
  },
  thresholds: { overbought: 80, midline: 50, oversold: 20 },
  footnote: "Based on current constituents; survivorship bias applies.",
};

const advanceDecline = {
  points: dates.map((date, i) => ({
    date,
    advances: 300 + (i % 7) * 20,
    declines: i === 10 ? 0 : 400 - (i % 5) * 15,
    unchanged: 3,
    ad_ratio: i === 10 ? null : 0.8 + (i % 5) / 10,
    ad_ratio_smooth: i < 3 ? null : 0.9 + (i % 4) / 10,
    ad_line: 1000 + i * 12,
  })),
  index: [],
  index_name: "Nifty 500",
  smoothing_window: 10,
  footnote: "Based on current constituents; survivorship bias applies.",
};

const globalCards = [
  {
    name: "Dow Jones",
    ticker: "^DJI",
    last_close: 41234.56,
    change_pct: 0.42,
    last_date: dates.at(-1),
    spark: dates.slice(-20).map((date, i) => ({ date, value: 41000 + i * 12 })),
  },
  // a market that failed entirely
  { name: "Nasdaq", ticker: "^IXIC", last_close: null, change_pct: null, last_date: null, spark: [] },
  // a market with a single point (no previous close -> no % change)
  {
    name: "Nikkei 225",
    ticker: "^N225",
    last_close: 39000,
    change_pct: null,
    last_date: dates.at(-1),
    spark: [{ date: dates.at(-1), value: 39000 }],
  },
  {
    name: "KOSPI",
    ticker: "^KS11",
    last_close: 2650.1,
    change_pct: -1.2,
    last_date: dates.at(-2),
    spark: dates.slice(-20).map((date, i) => ({ date, value: 2700 - i * 3 })),
  },
  {
    name: "Hang Seng",
    ticker: "^HSI",
    last_close: 19000,
    change_pct: 0,
    last_date: dates.at(-1),
    spark: dates.slice(-20).map((date, i) => ({ date, value: i % 2 ? null : 19000 + i })),
  },
];

const macro = {
  series: [
    {
      name: "USD/INR",
      ticker: "INR=X",
      points: dates.map((date, i) => ({ date, value: 83 + i / 50 })),
      last_value: 83.8,
      change_pct: 0.9,
      note: "Rupees per dollar — a rising line means a weaker rupee.",
    },
    // this one failed on Yahoo: no points at all
    { name: "Dollar Index", ticker: "DX-Y.NYB", points: [], last_value: null, change_pct: null, note: null },
    // all-null values
    {
      name: "US 10-Year Yield",
      ticker: "^TNX",
      points: dates.map((date) => ({ date, value: null })),
      last_value: null,
      change_pct: null,
      note: null,
    },
  ],
};

const commodities = {
  series: [
    {
      name: "Gold",
      ticker: "GC=F",
      points: dates.map((date, i) => ({ date, value: 2300 + i })),
      last_value: 2340,
      change_pct: 1.7,
      note: null,
    },
    {
      name: "Silver",
      ticker: "SI=F",
      points: dates.map((date, i) => ({ date, value: i < 20 ? null : 27 + i / 10 })),
      last_value: 29,
      change_pct: null,
      note: null,
    },
    { name: "Brent Crude (UK Oil)", ticker: "BZ=F", points: [], last_value: null, change_pct: null, note: null },
  ],
};

// ETFs: one that never traded, one listed mid-range (partial), one whose
// spark is all nulls, one with a single point - plus a benchmark that failed.
const etfGroups = ["Banking", "Sector", "Theme", "Broad market"];
const etfSpark = (n, fn) => dates.slice(-n).map((date, i) => ({ date, value: fn(i) }));
const etfs = [
  {
    symbol: "BANKBEES", ticker: "BANKBEES.NS", name: "Nippon Nifty Bank ETF", group: "Banking",
    last_value: 512.4, last_date: dates.at(-1), change_pct: 8.4, relative_pct: 0.1,
    first_date: dates[0], partial: false, spark: etfSpark(30, (i) => 480 + i),
  },
  {
    symbol: "PSUBNKBEES", ticker: "PSUBNKBEES.NS", name: "Nippon Nifty PSU Bank ETF", group: "Banking",
    last_value: null, last_date: null, change_pct: null, relative_pct: null,
    first_date: null, partial: false, spark: [], // never returned any data
  },
  {
    symbol: "MODEFENCE", ticker: "MODEFENCE.NS", name: "Motilal Oswal Defence ETF", group: "Theme",
    last_value: 92.1, last_date: dates.at(-1), change_pct: 22.5, relative_pct: 14.2,
    first_date: dates[25], partial: true, spark: etfSpark(15, (i) => 75 + i * 1.1),
  },
  {
    symbol: "GROWWEV", ticker: "GROWWEV.NS", name: "Groww EV & New Age Auto ETF", group: "Theme",
    last_value: null, last_date: dates.at(-1), change_pct: null, relative_pct: null,
    first_date: dates[0], partial: false, spark: etfSpark(20, () => null),
  },
  {
    symbol: "NIFTYBEES", ticker: "NIFTYBEES.NS", name: "Nippon Nifty 50 ETF", group: "Broad market",
    last_value: 268.5, last_date: dates.at(-1), change_pct: null, relative_pct: null,
    first_date: dates.at(-1), partial: true, spark: [{ date: dates.at(-1), value: 268.5 }],
  },
];

const etfList = {
  etfs,
  groups: etfGroups,
  benchmark_name: "Nifty 500",
  benchmark_change_pct: null, // benchmark failed on Yahoo
  range: "1Y",
};

const etfCompare = {
  series: [
    { symbol: "BANKBEES", name: "Nippon Nifty Bank ETF", points: dates.map((date, i) => ({ date, value: 480 + i })) },
    { symbol: "PSUBNKBEES", name: "Nippon Nifty PSU Bank ETF", points: [] },
    { symbol: "MODEFENCE", name: "Motilal Oswal Defence ETF", points: dates.map((date, i) => ({ date, value: i < 25 ? null : 75 + i })) },
    { symbol: "NIFTYBEES", name: "Nippon Nifty 50 ETF", points: [{ date: dates.at(-1), value: 268.5 }] },
  ],
  benchmark: null, // overlay index returned nothing
  benchmark_name: "Nifty 500",
  range: "1Y",
};

const meta = {
  last_updated: new Date().toISOString().slice(0, 19),
  last_computed: new Date().toISOString().slice(0, 19),
  index_name: "Nifty 500",
  index_ticker: "^CRSLDX",
  index_note: "^CRSLDX returned no data",
  demo_data: false,
  has_data: true,
  n_prices: 1180234,
  n_tickers: 766,
  n_stocks: 755,
  universe_count: 755,
  universe_file: "universe.csv",
  first_date: dates[0],
  last_date: dates.at(-1),
  ranges: ["1M", "3M", "6M", "1Y", "3Y", "5Y"],
};

const status = {
  tickers: [
    { ticker: "RELIANCE.NS", symbol: "RELIANCE", name: "Reliance", kind: "stock", status: "ok", message: "", first_date: dates[0], last_date: dates.at(-1), n_rows: 1200 },
    { ticker: "^CRSLDX", symbol: "^CRSLDX", name: "Nifty 500", kind: "index", status: "empty", message: "no data returned", first_date: null, last_date: null, n_rows: 0 },
  ],
  n_ok: 1,
  n_problem: 1,
};

const refreshState = {
  running: false,
  progress: 1,
  message: "Done",
  started_at: null,
  finished_at: new Date().toISOString().slice(0, 19),
  ok: true,
  summary: "412,330 rows added across 764 tickers · 2 tickers failed",
  rows_added: 412330,
  tickers_updated: 764,
  failures: [["^CRSLDX", "no data returned"]],
  error: null,
};

const routes = {
  "/api/meta": meta,
  "/api/breadth": breadth,
  "/api/advance-decline": advanceDecline,
  "/api/global": globalCards,
  "/api/global-chart": () => ({ series: [] }),
  "/api/macro": macro,
  "/api/commodities": commodities,
  "/api/etfs": etfList,
  "/api/etfs/compare": etfCompare,
  "/api/status": status,
  "/api/refresh/status": refreshState,
  "/api/health": { status: "ok" },
};

const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, "http://x").pathname;
  const body = routes[pathname];
  res.writeHead(body ? 200 : 404, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body ?? { detail: "not found" }));
});

server.listen(8099, "127.0.0.1", () => {
  console.log("hostile stub API on http://127.0.0.1:8099");
});
