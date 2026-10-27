import { useState } from "react";
import { Play, Download, AlertCircle, CheckCircle, Clock } from "lucide-react";
import { Card } from "./ui/card";

interface ScannerCriteria {
  ema_fast: number;
  ema_slow: number;
  high_lookback: number;
  high_threshold: number;
  rs_lookback: number;
  min_bars: number;
  benchmark: string;
}

interface ScannerResult {
  rank: number;
  symbol: string;
  name: string;
  close: number;
  ema50: number;
  ema150: number;
  high_52w: number;
  pct_below_high: number;
  pct_vs_ema50: number;
  rs_ratio: number;
  rs_score_pct: number;
  rs_percentile: number;
}

interface ScanResponse {
  results: ScannerResult[];
  count: number;
  timestamp: string;
  criteria: ScannerCriteria;
  total_scanned: number;
  passed: number;
  skipped: number;
}

export function ScannerPage() {
  const [criteria, setCriteria] = useState<ScannerCriteria>({
    ema_fast: 50,
    ema_slow: 150,
    high_lookback: 260,
    high_threshold: 0.70,
    rs_lookback: 126,
    min_bars: 260,
    benchmark: "^CRSLDX",
  });

  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    try {
      const response = await fetch("/api/scanner/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(criteria),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data: ScanResponse = await response.json();
      setResults(data);
    } catch (error) {
      console.error("Scan failed:", error);
      setError(error instanceof Error ? error.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const handleExportCSV = () => {
    if (!results || results.results.length === 0) return;

    const headers = [
      "Rank",
      "Symbol",
      "Close",
      "EMA50",
      "EMA150",
      "52W High",
      "% Below 52W High",
      "Close vs EMA50 (%)",
      "RS Ratio",
      "RS Score (%)",
      "RS Percentile",
    ];

    const rows = results.results.map((r) => [
      r.rank.toString(),
      r.symbol,
      r.close.toFixed(2),
      r.ema50.toFixed(2),
      r.ema150.toFixed(2),
      r.high_52w.toFixed(2),
      r.pct_below_high.toFixed(2),
      r.pct_vs_ema50.toFixed(2),
      r.rs_ratio.toFixed(4),
      r.rs_score_pct.toFixed(2),
      r.rs_percentile.toString(),
    ]);

    const csvContent = [headers, ...rows].map((row) => row.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `scan_results_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-ink">Stock Scanner</h1>
        <p className="mt-2 text-muted">
          Scan NSE stocks based on technical criteria and relative strength
        </p>
      </div>

      {/* Configuration */}
      <Card>
        <h2 className="mb-4 text-lg font-semibold text-ink">Scanner Configuration</h2>
        
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* EMA Fast */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Fast EMA Period
            </label>
            <input
              type="number"
              value={criteria.ema_fast}
              onChange={(e) =>
                setCriteria({ ...criteria, ema_fast: Number(e.target.value) })
              }
              min={10}
              max={200}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* EMA Slow */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Slow EMA Period
            </label>
            <input
              type="number"
              value={criteria.ema_slow}
              onChange={(e) =>
                setCriteria({ ...criteria, ema_slow: Number(e.target.value) })
              }
              min={50}
              max={300}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* High Lookback */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              52W High Lookback (days)
            </label>
            <input
              type="number"
              value={criteria.high_lookback}
              onChange={(e) =>
                setCriteria({ ...criteria, high_lookback: Number(e.target.value) })
              }
              min={100}
              max={500}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* High Threshold */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Min % of 52W High
            </label>
            <input
              type="number"
              value={criteria.high_threshold * 100}
              onChange={(e) =>
                setCriteria({
                  ...criteria,
                  high_threshold: Number(e.target.value) / 100,
                })
              }
              min={50}
              max={100}
              step={5}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* RS Lookback */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              RS Lookback (days)
            </label>
            <input
              type="number"
              value={criteria.rs_lookback}
              onChange={(e) =>
                setCriteria({ ...criteria, rs_lookback: Number(e.target.value) })
              }
              min={50}
              max={252}
              step={10}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          {/* Benchmark */}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Benchmark
            </label>
            <select
              value={criteria.benchmark}
              onChange={(e) =>
                setCriteria({ ...criteria, benchmark: e.target.value })
              }
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
            >
              <option value="^CRSLDX">Nifty 500</option>
              <option value="^NSEI">Nifty 50</option>
              <option value="^NSEBANK">Bank Nifty</option>
            </select>
          </div>
        </div>

        {/* Scan Criteria Info */}
        <div className="mt-6 rounded-lg bg-surface-2 p-4">
          <h3 className="mb-2 text-sm font-semibold text-ink">Scan Criteria (All Must Be True):</h3>
          <ul className="space-y-1 text-sm text-muted">
            <li>• Close ≥ EMA{criteria.ema_fast}</li>
            <li>• Close ≥ {(criteria.high_threshold * 100).toFixed(0)}% × 52-Week High</li>
            <li>• EMA{criteria.ema_fast} ≥ EMA{criteria.ema_slow} (Uptrend)</li>
          </ul>
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

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-400">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}
      </Card>

      {/* Results */}
      {results && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-blue-100 p-2 dark:bg-blue-900/20">
                  <Clock className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-sm text-muted">Total Scanned</p>
                  <p className="text-2xl font-bold text-ink">{results.total_scanned}</p>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-green-100 p-2 dark:bg-green-900/20">
                  <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <p className="text-sm text-muted">Passed Criteria</p>
                  <p className="text-2xl font-bold text-ink">{results.passed}</p>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-yellow-100 p-2 dark:bg-yellow-900/20">
                  <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                </div>
                <div>
                  <p className="text-sm text-muted">Skipped</p>
                  <p className="text-2xl font-bold text-ink">{results.skipped}</p>
                </div>
              </div>
            </Card>
          </div>

          {/* Results Table */}
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-ink">
                Scan Results ({results.count} stocks)
              </h2>
              <div className="text-sm text-muted">
                Benchmark: {results.criteria.benchmark === "^CRSLDX" ? "Nifty 500" : 
                           results.criteria.benchmark === "^NSEI" ? "Nifty 50" : "Bank Nifty"}
              </div>
            </div>

            {results.results.length === 0 ? (
              <div className="rounded-lg border border-dashed border-line bg-surface-2/50 py-16 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-surface-2">
                  <svg className="h-8 w-8 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <h3 className="mb-2 text-lg font-semibold text-ink">No Stocks Found</h3>
                <p className="mb-4 text-sm text-muted">
                  No stocks matched the selected criteria.
                </p>
                <p className="text-xs text-muted">
                  Try adjusting the parameters or lowering the threshold to broaden your search.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line bg-surface-2">
                      <th className="px-3 py-2 text-left font-medium text-ink">Rank</th>
                      <th className="px-3 py-2 text-left font-medium text-ink">Symbol</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">Close</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">EMA50</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">EMA150</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">52W High</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">% Below 52W</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">% vs EMA50</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">RS Score</th>
                      <th className="px-3 py-2 text-right font-medium text-ink">RS %ile</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.results.map((stock) => (
                      <tr
                        key={stock.symbol}
                        className="border-b border-line/50 hover:bg-surface-2/50"
                      >
                        <td className="px-3 py-2 font-medium text-ink">
                          {stock.rank}
                        </td>
                        <td className="px-3 py-2 font-medium text-ink">
                          {stock.symbol}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          ₹{stock.close.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          ₹{stock.ema50.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          ₹{stock.ema150.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          ₹{stock.high_52w.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {stock.pct_below_high.toFixed(2)}%
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {stock.pct_vs_ema50.toFixed(2)}%
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {stock.rs_score_pct.toFixed(2)}%
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {stock.rs_percentile}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
