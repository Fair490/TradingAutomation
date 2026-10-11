/**
 * Scanner page - Technical stock scanner with configurable criteria.
 */

import { useState } from "react";
import { Download, Play, Settings } from "lucide-react";
import { Card } from "./ui";

interface ScanResult {
  symbol: string;
  name: string;
  ticker: string;
  close: number;
  close_vs_high_252: number;
  sma50: number | null;
  sma150: number | null;
  sma200: number | null;
  rs: number | null;
  rising_rs: boolean;
  passes_close_vs_high: boolean;
  passes_above_sma50: boolean;
  passes_sma50_above_sma150: boolean;
  passes_rising_sma200: boolean;
  passes_rs_at_high: boolean;
}

interface ScanResponse {
  results: ScanResult[];
  count: number;
  benchmark: string;
  criteria: Record<string, any>;
}

interface ScanCriteria {
  benchmark_ticker: string;
  min_close_vs_high: number;
  require_above_sma50: boolean;
  require_sma50_above_sma150: boolean;
  require_rising_sma200: boolean;
  require_rs_at_high: boolean;
  lookback_days: number;
}

export function ScannerPage() {
  const [criteria, setCriteria] = useState<ScanCriteria>({
    benchmark_ticker: "^CRSLDX",
    min_close_vs_high: 0.80,
    require_above_sma50: true,
    require_sma50_above_sma150: true,
    require_rising_sma200: true,
    require_rs_at_high: true,
    lookback_days: 252,
  });

  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<ScanResponse | null>(null);

  const handleScan = async () => {
    setScanning(true);
    try {
      const response = await fetch("/api/scanner/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(criteria),
      });
      const data: ScanResponse = await response.json();
      setResults(data);
    } catch (error) {
      console.error("Scan failed:", error);
    } finally {
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

    const rows = results.results.map((r) => [
      r.symbol,
      r.name,
      r.close.toFixed(2),
      r.close_vs_high_252.toFixed(2),
      r.sma50?.toFixed(2) || "",
      r.sma150?.toFixed(2) || "",
      r.sma200?.toFixed(2) || "",
      r.rs?.toFixed(2) || "",
      r.rising_rs ? "Yes" : "No",
    ]);

    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.join(",")),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `scanner-results-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

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
            <label className="mb-1 block text-sm font-medium text-ink">
              Benchmark
            </label>
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
            <label className="mb-1 block text-sm font-medium text-ink">
              Lookback Days
            </label>
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
          <div className="flex items-center gap-2 sm:col-span-2 lg:col-span-3">
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
        <div className="mt-6 flex gap-3">
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent/90 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {scanning ? "Scanning..." : "Start Scan"}
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
        </div>
      </Card>

      {/* Results */}
      {results && (
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-ink">
              Scan Results ({results.count} stocks)
            </h2>
            <div className="text-sm text-muted">
              Benchmark: {results.benchmark}
            </div>
          </div>

          {results.results.length === 0 ? (
            <div className="py-12 text-center text-muted">
              No stocks matched the criteria. Try adjusting the parameters.
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
                  {results.results.map((stock) => (
                    <tr
                      key={stock.ticker}
                      className="border-b border-line/50 hover:bg-surface-2/50"
                    >
                      <td className="px-3 py-2 font-medium text-ink">
                        {stock.symbol}
                      </td>
                      <td className="px-3 py-2 text-muted">{stock.name}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.close.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.close_vs_high_252.toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.sma50?.toFixed(2) || "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.sma150?.toFixed(2) || "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.sma200?.toFixed(2) || "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {stock.rs?.toFixed(2) || "—"}
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
