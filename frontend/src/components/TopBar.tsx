/** Sticky header: identity, freshness, range buttons, theme and refresh. */

import clsx from "clsx";
import { Activity, Moon, RefreshCw, Sun, TrendingUp } from "lucide-react";
import type { Meta, RangeKey } from "../lib/api";
import { RS_BENCHMARKS } from "../lib/rs";
import { mediumDate, timeAgo } from "../lib/format";
import { Pill, Segmented } from "./ui";

const RANGES: RangeKey[] = ["1M", "3M", "6M", "1Y", "3Y", "5Y"];

export function TopBar({
  meta,
  range,
  onRange,
  theme,
  onTheme,
  onRefresh,
  running,
  progress,
  rsOn,
  onRsToggle,
  rsBenchmark,
  onRsBenchmark,
}: {
  meta?: Meta;
  range: RangeKey;
  onRange: (next: RangeKey) => void;
  theme: "light" | "dark";
  onTheme: (next: "light" | "dark") => void;
  onRefresh: () => void;
  running: boolean;
  progress: number;
  rsOn: boolean;
  onRsToggle: () => void;
  rsBenchmark: string;
  onRsBenchmark: (ticker: string) => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-accent text-white shadow-sm">
            <Activity size={17} strokeWidth={2.4} />
          </span>
          <div className="leading-tight">
            <h1 className="text-[15px] font-semibold tracking-[-0.015em] text-ink">
              Market Health
            </h1>
            <p className="text-[11.5px] text-muted">
              {meta?.n_stocks
                ? `${meta.n_stocks} stocks · ${meta.index_name ?? "index"} overlay`
                : "Nifty Total Market universe"}
            </p>
          </div>
        </div>

        <div className="hidden items-center gap-2 lg:flex">
          <span className="h-5 w-px bg-line" />
          <Pill tone={meta?.last_updated ? "neutral" : "warn"}>
            <span
              className={clsx(
                "h-1.5 w-1.5 rounded-full",
                running ? "animate-pulse bg-accent" : meta?.last_updated ? "bg-up" : "bg-faint",
              )}
            />
            Updated {timeAgo(meta?.last_updated ?? null)}
          </Pill>
          {meta?.last_date ? (
            <Pill>Data through {mediumDate(meta.last_date)}</Pill>
          ) : null}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* RS toggle + benchmark selector */}
          <div className="hidden items-center gap-1 rounded-full border border-line bg-surface px-1.5 py-1 md:flex">
            <button
              type="button"
              onClick={onRsToggle}
              className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold transition ${
                rsOn ? "bg-up/15 text-up" : "text-muted hover:text-ink"
              }`}
              title="Relative Strength vs the selected benchmark"
            >
              <TrendingUp size={12} />
              RS
            </button>
            {rsOn ? (
              <select
                value={rsBenchmark}
                onChange={(e) => onRsBenchmark(e.target.value)}
                className="rounded-md bg-transparent px-1 py-0.5 text-[11.5px] font-medium text-ink outline-none"
              >
                {RS_BENCHMARKS.map((b) => (
                  <option key={b.ticker} value={b.ticker}>
                    {b.label}
                  </option>
                ))}
              </select>
            ) : null}
          </div>

          <Segmented<RangeKey>
            ariaLabel="Date range"
            value={range}
            onChange={onRange}
            options={RANGES}
          />

          <button
            type="button"
            onClick={() => onTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle colour theme"
            className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-surface text-muted transition hover:text-ink"
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          <button
            type="button"
            onClick={onRefresh}
            disabled={running}
            className={clsx(
              "flex items-center gap-2 rounded-full px-3.5 py-2 text-[12.5px] font-semibold transition",
              running
                ? "cursor-progress bg-accent/15 text-accent"
                : "bg-accent text-white hover:brightness-110 active:brightness-95",
            )}
          >
            <RefreshCw size={14} className={running ? "animate-spin" : undefined} />
            {running ? `${Math.round(progress * 100)}%` : "Refresh data"}
          </button>
        </div>
      </div>

      <div className="h-[2px] w-full bg-transparent">
        {running ? (
          <div
            className="h-[2px] bg-accent transition-all duration-500"
            style={{ width: `${Math.max(progress * 100, 3)}%` }}
          />
        ) : null}
      </div>
    </header>
  );
}
