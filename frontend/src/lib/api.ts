/**
 * API client and type definitions for the Market Health Dashboard.
 * Types match backend/api/schemas.py exactly.
 */

export type RangeKey = "1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y" | "Max";
export type Interval = "D" | "W" | "M";

export interface Point {
  date: string;
  value: number | null;
}

export interface IndexPoint {
  date: string;
  close: number | null;
}

export interface MetaResponse {
  last_updated: string | null;
  last_computed: string | null;
  index_name: string | null;
  index_ticker: string | null;
  index_note: string | null;
  demo_data: boolean;
  has_data: boolean;
  n_prices: number;
  n_tickers: number;
  n_stocks: number;
  universe_count: number;
  universe_file: string;
  first_date: string | null;
  last_date: string | null;
  ranges: string[];
}

// Backward compatibility alias
export type Meta = MetaResponse;

export interface BreadthPoint {
  date: string;
  pct_above: number | null;
  above_below: number | null;
  n_valid: number;
  n_above: number;
  n_below: number;
}

export interface BreadthLatest {
  date: string;
  pct_above: number | null;
  above_below: number | null;
  n_above: number;
  n_below: number;
  n_valid: number;
  change_1d: number | null;
  change_1w: number | null;
}

export interface Thresholds {
  overbought: number;
  midline: number;
  oversold: number;
}

export interface BreadthResponse {
  points: BreadthPoint[];
  index: IndexPoint[];
  index_name: string;
  latest: BreadthLatest | null;
  thresholds: Thresholds;
  footnote: string;
}

export interface AdvanceDeclinePoint {
  date: string;
  advances: number;
  declines: number;
  unchanged: number;
  ad_ratio: number | null;
  ad_ratio_smooth: number | null;
  ad_line: number | null;
}

export interface AdvanceDeclineResponse {
  points: AdvanceDeclinePoint[];
  index: IndexPoint[];
  index_name: string;
  smoothing_window: number;
  latest_daily_ratio: number | null;
  latest_avg_ratio: number | null;
  divergence: boolean;
  footnote: string;
}

// Backward compatibility alias
export type AdResponse = AdvanceDeclineResponse;
export type AdPoint = AdvanceDeclinePoint;

export interface GlobalCard {
  name: string;
  ticker: string;
  last_close: number | null;
  change_pct: number | null;
  last_date: string | null;
  stale: boolean;
  spark: Point[];
  change_1m: number | null;
  change_1y: number | null;
  change_5y: number | null;
  unit: string;
  ma50: number | null;
  ma150: number | null;
}

export interface MovingAverages {
  ma50: (number | null)[];
  ma150: (number | null)[];
}

export interface NamedSeries {
  name: string;
  ticker: string;
  points: Point[];
  last_value: number | null;
  change_pct: number | null;
  note: string | null;
  unit: string;
  change_1m: number | null;
  change_1y: number | null;
  change_5y: number | null;
  moving_averages: MovingAverages | null;
}

export interface SeriesResponse {
  series: NamedSeries[];
}

export interface EtfPeriod {
  change_pct: number | null;
  relative_pct: number | null;
}

export interface EtfSummary {
  symbol: string;
  ticker: string;
  name: string;
  group: string;
  last_value: number | null;
  last_date: string | null;
  change_pct: number | null;
  relative_pct: number | null;
  first_date: string | null;
  partial: boolean;
  spark: Point[];
  periods: Record<string, EtfPeriod>;
  pct_from_52w_high: number | null;
  pct_from_50dma: number | null;
  pct_from_150dma: number | null;
}

export interface EtfListResponse {
  etfs: EtfSummary[];
  groups: string[];
  benchmark_name: string;
  benchmark_change_pct: number | null;
  range: string;
}

export interface EtfSeries {
  symbol: string;
  name: string;
  points: Point[];
}

export interface EtfCompareResponse {
  series: EtfSeries[];
  benchmark: EtfSeries | null;
  benchmark_name: string;
  range: string;
}

export interface TickerStatus {
  ticker: string;
  symbol: string | null;
  name: string | null;
  kind: string | null;
  status: string | null;
  message: string | null;
  first_date: string | null;
  last_date: string | null;
  n_rows: number | null;
}

export interface StatusResponse {
  tickers: TickerStatus[];
  n_ok: number;
  n_problem: number;
}

export interface RefreshState {
  running: boolean;
  progress: number;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  ok: boolean | null;
  summary: string | null;
  rows_added: number;
  tickers_updated: number;
  failures: string[][];
  error: string | null;
}

export interface RefreshRequest {
  full_rebuild: boolean;
}

export async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
