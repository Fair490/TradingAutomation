/**
 * Scanner page - Technical stock scanner with configurable criteria.
 *
 * Data handling rules (learned the hard way):
 * - a 200 is not the same as a usable payload: the status code, the JSON and
 *   the response shape are all checked before anything is rendered;
 * - a backend failure is shown to the user, never only written to the console;
 * - a legitimate zero-match scan is explained with the diagnostics the API
 *   returns instead of being conflated with missing data or a server error.
 */

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Download, Loader2, Play, Settings } from "lucide-react";
import { Card } from "./ui";
import type { ApiErrorDetail, ScanCriteria, ScanResponse, ScanResult } from "../lib/api";

/** The scan is a normal synchronous request; guard it against hanging. */
const SCAN_TIMEOUT_MS = 120_000;

const CRITERION_LABELS: Record<string, string> = {
  close_vs_high: "Close vs high",
  above_sma50: "Close ≥ 50DMA",
  sma50_above_sma150: "50DMA ≥ 150DMA",
  rising_sma200: "200DMA rising",
  rs_at_high: "RS at high",
};

const SKIP_LABELS: Record<string, string> = {
  no_price_history: "no price history stored",
  invalid_prices: "prices missing/invalid",
  insufficient_history: "not enough sessions",
  stale_data: "data too old",
};

type ScanErrorKind = "http" | "network" | "timeout" | "malformed";

interface ScanError {
  kind: ScanErrorKind;
  message: string;
  code?: string;
  status?: number;
}

function messageFromErrorBody(payload: unknown): { message: string | null; code?: string } {
  if (!payload || typeof payload !== "object") return { message: null };
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const structured = detail as Partial<ApiErrorDetail>;
    return {
      message: typeof structured.message === "string" ? structured.message : null,
      code: typeof structured.code === "string" ? structured.code : undefined,
    };
  }
  if (Array.isArray(detail)) {
    // pydantic validation errors: [{loc, msg, type}, ...]
    const parts = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const entry = item as { loc?: unknown[]; msg?: string };
        const field = Array.isArray(entry.loc) ? entry.loc.slice(1).join(".") : "";
        return entry.msg ? `${field ? `${field}: ` : ""}${entry.msg}` : null;
      })
      .filter((part): part is string => Boolean(part));
    if (parts.length) return { message: parts.join("; "), code: "validation_error" };
  }
  return { message: null };
}

function isScanResponse(value: unknown): value is ScanResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ScanResponse>;
  return Array.isArray(candidate.results) && typeof candidate.count === "number";
}

export function ScannerPage() {
  const [criteria, setCriteria] = useState<ScanCriteria>({
    benchmark_ticker: "^CRSLDX",
    min_close_vs_high: 0.8,
    require_above_sma50: true,
    require_sma50_above_sma150: true,
    require_rising_sma200: true,
    require_rs_at_high: true,
    lookback_days: 252,
  });

  const [scanning, setScanning] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [results, setResults] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<ScanError | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    if (!scanning) return;
    const started = Date.now();
    setElapsedSeconds(0);
    const timer = window.setInterval(
      () => setElapsedSeconds(Math.round((Date.now() - started) / 1000)),
      500,
    );
    return () => window.clearInterval(timer);
  }, [scanning]);

  const handleScan = async () => {
    if (inFlight.current) return; // double-click / duplicate submit guard
    inFlight.current = true;
    setScanning(true);
    setError(null);
    setResults(null);

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), SCAN_TIMEOUT_MS);
    try {
      const response = await fetch("/api/scanner/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(criteria),
        signal: controller.signal,
      });

      const raw = await response.text();
      let payload: unknown = null;
      let parseFailed = false;
      try {
        payload = raw ? JSON.parse(raw) : null;
      } catch {
        parseFailed = true;
      }

      if (!response.ok) {
        const { message, code } = messageFromErrorBody(payload);
        setError({
          kind: "http",
          status: response.status,
          code,
          message:
            message ??
            `The scanner request failed with HTTP ${response.status} ${response.statusText}.`,
        });
        return;
      }

      if (parseFailed) {
        setError({
          kind: "malformed",
          message: "The backend returned a response that is not valid JSON.",
        });
        return;
      }

      if (!isScanResponse(payload)) {
        setError({
          kind: "malformed",
          message:
            "The scan response did not contain the expected results payload " +
            "(missing results/count). The backend may be running a different version.",
        });
        return;
      }

      setResults({
        results: payload.results,
        count: payload.count,
        benchmark:
          typeof payload.benchmark === "string" ? payload.benchmark : criteria.benchmark_ticker,
        criteria: payload.criteria ?? {},
        diagnostics: payload.diagnostics ?? null,
      });
    } catch (caught) {
      if (controller.signal.aborted) {
        setError({
          kind: "timeout",
          message: `The scan did not finish within ${Math.round(
            SCAN_TIMEOUT_MS / 1000,
          )} seconds and was cancelled. Try a shorter lookback or check the backend log.`,
        });
      } else {
        setError({
          kind: "network",
          message:
            "Could not reach the backend. Check that the API server is running, then try again.",
        });
        console.error("Scanner request failed:", caught);
      }
    } finally {
      window.clearTimeout(timeout);
      inFlight.current = false;
      setScanning(false);
    }
  };

  const handleExportCSV = () => {
    if (!results || results.results.length === 0) return;

    const headers = [
      "Symbol",
      "Name",
      "Close",
      "Close vs 252 High (%)",
      "SMA50",
      "SMA150",
      "SMA200",
      "RS",
      "Rising RS",
    ];

    const number = (value: number | null | undefined) =>
      value === null || value === undefined ? "" : value.toFixed(2);

    const rows = results.results.map((r) => [
      r.symbol,
      r.name,
      number(r.close),
      number(r.close_vs_high_252),
      number(r.sma50),
      number(r.sma150),
      number(r.sma200),
      number(r.rs),
      r.rising_rs ? "Yes" : "No",
    ]);

    const csvContent = [headers.join(","), ...rows.map((row) => row.join(","))].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `scanner-results-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const diagnostics = results?.diagnostics ?? null;

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink">Stock Scanner</h1>
        <p className="mt-1 text-sm text-muted">
          Scan stocks against technical criteria to find high-quality setups
        </p>
      </div>

      {/* Criteria Panel */}
      <Card className="mb-6">
        <div className="mb-4 flex items-center gap-2">
          <Settings className="h-5 w-5 text-accent" />
          <h2 className="text-lg font-semibold text-ink">Scan Criteria</h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Benchmark */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Benchmark</label>
            <select
              value={criteria.benchmark_ticker}
              onChange={(e) =>
                setCriteria({ ...criteria, benchmark_ticker: e.target.value })
              }
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            >
              <option value="^CRSLDX">Nifty 500</option>
              <option value="^NSEI">Nifty 50</option>
              <option value="^NSEBANK">Bank Nifty</option>
            </select>
          </div>

          {/* Close vs High */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Min Close vs 252 High (%)
            </label>
            <input
              type="number"
              value={criteria.min_close_vs_high * 100}
              onChange={(e) =>
                setCriteria({
                  ...criteria,
                  min_close_vs_high: Number(e.target.value) / 100,
                })
              }
              min={50}
              max={100}
              step={5}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* Lookback Days */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Lookback Days</label>
            <input
              type="number"
              value={criteria.lookback_days}
              onChange={(e) =>
                setCriteria({
                  ...criteria,
                  lookback_days: Number(e.target.value),
                })
              }
              min={50}
              max={500}
              step={10}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* Checkboxes */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 sm:col-span-2 lg:col-span-3">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={criteria.require_above_sma50}
                onChange={(e) =>
                  setCriteria({
                    ...criteria,
                    require_above_sma50: e.target.checked,
                  })
                }
                className="h-4 w-4 rounded border-line"
              />
              <span className="text-sm text-ink">Close ≥ SMA50</span>
            </label>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={criteria.require_sma50_above_sma150}
                onChange={(e) =>
                  setCriteria({
                    ...criteria,
                    require_sma50_above_sma150: e.target.checked,
                  })
                }
                className="h-4 w-4 rounded border-line"
              />
              <span className="text-sm text-ink">SMA50 ≥ SMA150</span>
            </label>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={criteria.require_rising_sma200}
                onChange={(e) =>
                  setCriteria({
                    ...criteria,
                    require_rising_sma200: e.target.checked,
                  })
                }
                className="h-4 w-4 rounded border-line"
              />
              <span className="text-sm text-ink">Rising SMA200</span>
            </label>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={criteria.require_rs_at_high}
                onChange={(e) =>
                  setCriteria({
                    ...criteria,
                    require_rs_at_high: e.target.checked,
                  })
                }
                className="h-4 w-4 rounded border-line"
              />
              <span className="text-sm text-ink">RS at 252-day High</span>
            </label>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent/90 disabled:opacity-50"
          >
            {scanning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {scanning
              ? `Scanning… ${elapsedSeconds}s`
              : elapsedSeconds
                ? "Scan again"
                : "Start Scan"}
          </button>

          {results && results.count > 0 && (
            <button
              onClick={handleExportCSV}
              className="flex items-center gap-2 rounded-lg bg-surface-2 px-4 py-2 text-sm font-medium text-ink transition hover:bg-surface"
            >
              <Download className="h-4 w-4" />
              Export CSV
            </button>
          )}

          {scanning && (
            <span className="text-xs text-muted">
              Scanning {diagnostics?.universe_size ?? ""} symbols against stored history…
            </span>
          )}
        </div>
      </Card>

      {/* Error banner: backend failures are always visible, never console-only */}
      {error && (
        <div
          role="alert"
          className="mb-6 flex items-start gap-3 rounded-[var(--radius-card)] border border-down/40 bg-down/5 p-4"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-down" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">
              {error.kind === "timeout"
                ? "Scan timed out"
                : error.kind === "network"
                  ? "Backend unreachable"
                  : error.kind === "malformed"
                    ? "Unexpected response"
                    : `Scan failed${error.status ? ` (HTTP ${error.status})` : ""}`}
              {error.code ? (
                <span className="ml-2 rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] font-normal text-muted">
                  {error.code}
                </span>
              ) : null}
            </p>
            <p className="mt-1 text-sm text-muted">{error.message}</p>
            {(error.kind === "http" || error.kind === "timeout") && (
              <p className="mt-2 text-xs text-faint">
                This is a scanner failure, not an empty result: the last successful scan (if
                any) is unchanged. Check the backend log for details.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Diagnostics */}
      {results && diagnostics && (
        <Card className="mb-6">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold text-ink">Scan Diagnostics</h2>
            <span className="text-xs text-muted">
              {diagnostics.benchmark_name ?? diagnostics.benchmark} (
              {diagnostics.benchmark})
              {diagnostics.evaluation_date
                ? ` · data through ${diagnostics.evaluation_date}`
                : ""}
            </span>
          </div>

          <p className="mb-4 text-sm text-muted">{diagnostics.explanation}</p>

          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(
              [
                ["Universe", diagnostics.universe_size],
                ["Evaluated", diagnostics.symbols_evaluated],
                ["Matched", diagnostics.symbols_matched],
                ["Skipped", diagnostics.symbols_skipped],
              ] as const
            ).map(([label, value]) => (
              <div
                key={label}
                className="rounded-lg border border-line bg-surface-2/60 px-3 py-2"
              >
                <div className="text-[11px] uppercase tracking-[0.08em] text-faint">
                  {label}
                </div>
                <div className="font-mono text-lg text-ink">{value ?? "—"}</div>
              </div>
            ))}
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            {Object.entries(diagnostics.criterion_pass_counts ?? {}).map(([key, passed]) => {
              const active = diagnostics.criterion_active?.[key] !== false;
              return (
                <span
                  key={key}
                  title={active ? "Active filter" : "Filter switched off"}
                  className={
                    active
                      ? "rounded-full border border-line bg-surface-2 px-3 py-1 text-xs text-ink"
                      : "rounded-full border border-dashed border-line px-3 py-1 text-xs text-faint"
                  }
                >
                  {CRITERION_LABELS[key] ?? key}: {passed} / {diagnostics.symbols_evaluated}
                  {active ? "" : " (off)"}
                </span>
              );
            })}
          </div>

          {diagnostics.symbols_skipped > 0 && (
            <details className="mb-3 rounded-lg border border-line bg-surface-2/50 p-3">
              <summary className="cursor-pointer text-sm text-ink">
                Skipped symbols ({diagnostics.symbols_skipped})
              </summary>
              <ul className="mt-2 space-y-1 text-xs text-muted">
                {Object.entries(diagnostics.skipped ?? {}).map(([reason, count]) => (
                  <li key={reason}>
                    {count} × {SKIP_LABELS[reason] ?? reason}
                  </li>
                ))}
              </ul>
              {diagnostics.skipped_symbols?.length ? (
                <p className="mt-2 font-mono text-[11px] text-faint">
                  {diagnostics.skipped_symbols
                    .slice(0, 12)
                    .map((entry) => `${entry.symbol} (${SKIP_LABELS[entry.reason] ?? entry.reason})`)
                    .join(", ")}
                  {diagnostics.skipped_symbols.length > 12 ? ", …" : ""}
                </p>
              ) : null}
            </details>
          )}

          {(diagnostics.warnings ?? []).map((warning) => (
            <p key={warning} className="mb-2 flex items-start gap-2 text-xs text-muted">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
              <span>{warning}</span>
            </p>
          ))}

          <details className="rounded-lg border border-line bg-surface-2/50 p-3">
            <summary className="cursor-pointer text-sm text-ink">Timings</summary>
            <ul className="mt-2 grid gap-1 text-xs text-muted sm:grid-cols-3">
              {Object.entries(diagnostics.timings_ms ?? {}).map(([phase, ms]) => (
                <li key={phase} className="font-mono">
                  {phase}: {typeof ms === "number" ? `${ms.toFixed(0)} ms` : "—"}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-faint">
              Price field: {diagnostics.price_column} · required sessions:{" "}
              {diagnostics.required_sessions} · benchmark sessions:{" "}
              {diagnostics.benchmark_sessions}
            </p>
          </details>
        </Card>
      )}

      {/* Results */}
      {results && (
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-ink">
              Scan Results ({results.count ?? 0} stocks)
            </h2>
            <div className="text-sm text-muted">Benchmark: {results.benchmark}</div>
          </div>

          {!Array.isArray(results.results) || results.results.length === 0 ? (
            <div className="rounded-lg border border-dashed border-line bg-surface-2/50 py-16 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-surface-2">
                <svg
                  className="h-8 w-8 text-muted"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <h3 className="mb-2 text-lg font-semibold text-ink">No stocks matched</h3>
              <p className="mb-4 text-sm text-muted">
                {diagnostics?.explanation ??
                  "The scan completed and returned no matches for the selected criteria."}
              </p>
              <p className="text-xs text-muted">
                Try lowering “Min Close vs 252 High”, shortening the lookback, or
                unchecking a filter to broaden the search.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line bg-surface-2">
                    <th className="px-3 py-2 text-left font-medium text-ink">Symbol</th>
                    <th className="px-3 py-2 text-left font-medium text-ink">Name</th>
                    <th className="px-3 py-2 text-right font-medium text-ink">Close</th>
                    <th className="px-3 py-2 text-right font-medium text-ink">vs 252H</th>
                    <th className="px-3 py-2 text-right font-medium text-ink">SMA50</th>
                    <th className="px-3 py-2 text-right font-medium text-ink">SMA150</th>
                    <th className="px-3 py-2 text-right font-medium text-ink">SMA200</th>
                    <th className="px-3 py-2 text-right font-medium text-ink">RS</th>
                    <th className="px-3 py-2 text-center font-medium text-ink">Rising RS</th>
                  </tr>
                </thead>
                <tbody>
                  {results.results.map((stock: ScanResult) => (
                    <tr
                      key={stock.ticker}
                      className="border-b border-line/50 hover:bg-surface-2/50"
                    >
                      <td className="px-3 py-2 font-medium text-ink">{stock.symbol}</td>
                      <td className="px-3 py-2 text-muted">{stock.name}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.close?.toFixed(2) ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.close_vs_high_252 === null ||
                        stock.close_vs_high_252 === undefined
                          ? "—"
                          : `${stock.close_vs_high_252.toFixed(1)}%`}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.sma50?.toFixed(2) ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.sma150?.toFixed(2) ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.sma200?.toFixed(2) ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.rs?.toFixed(2) ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {stock.rising_rs ? (
                          <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
                            ✓
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                            —
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
