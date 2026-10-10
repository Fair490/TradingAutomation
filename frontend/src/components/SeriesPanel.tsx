/**
 * Panels 4 and 5 - macro (USD/INR, Dollar Index, US 10Y) and commodities
 * (Gold, Silver, Brent).  Separate charts by default, one rebased chart when
 * "Normalised" is on.
 *
 * Per-card footer shows 1M / 1Y / 5Y changes in the series unit; units are
 * pulled from the backend (USD/oz, USD/bbl, ₹/$, bps, price).
 *
 * Charts support:
 *  - Daily / Weekly / Monthly aggregation (weekly = last close of each week,
 *    monthly = last close of each month).
 *  - Optional 50-DMA and 150-DMA overlays.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RangeKey, SeriesResponse } from "../lib/api";
import { fetcher } from "../lib/api";
import {
  aggregate,
  axisDate,
  hasFinite,
  num,
  rebase,
  signed,
  thin,
  toneClass,
  type Interval,
} from "../lib/format";
import { useRsBenchmark } from "../lib/useRsBenchmark";
import { computeRS } from "../lib/rs";
import { RsSubchart } from "./RsSubchart";
import {
  Card,
  CardHeader,
  ChartSkeleton,
  EmptyNote,
  ErrorNote,
  SectionTitle,
  Switch,
} from "./ui";
import { ChartTooltip, useThemeColors, withAlpha } from "./charts";


export function SeriesPanel({
  title,
  hint,
  endpoint,
  range,
  theme,
  palette,
  decimals = 2,
  rsOn,
  rsBenchmark,
}: {
  title: string;
  hint?: string;
  endpoint: "macro" | "commodities";
  range: RangeKey;
  theme: string;
  palette: (keyof ReturnType<typeof useThemeColors>)[];
  decimals?: number;
  rsOn?: boolean;
  rsBenchmark?: string;
}) {
  const { data, error, isLoading } = useSWR<SeriesResponse>(
    `/api/${endpoint}?range=${range}`,
    fetcher,
    { keepPreviousData: true },
  );
  const [normalised, setNormalised] = useState(false);
  const [interval, setInterval] = useState<Interval>("D");
  const [showMA50, setShowMA50] = useState(false);
  const [showMA150, setShowMA150] = useState(false);
  const c = useThemeColors(theme);
  const { data: rsBenchData } = useRsBenchmark(
    rsOn && rsBenchmark ? rsBenchmark : "",
    range,
  );
  const colours = palette.map((token) => c[token]);

  const plottable = useMemo(
    () => (data?.series ?? []).filter((s) => hasFinite(s.points, "value")),
    [data],
  );

  const combined = useMemo(() => {
    if (!data) return [];
    const byDate = new Map<string, Record<string, number | null | string>>();
    for (const s of plottable) {
      // CORRECT ORDER: aggregate first, then thin for rendering
      const aggregated = aggregate(s.points, interval);
      const thinned = thin(aggregated, 520);
      for (const p of thinned) {
        const row = byDate.get(p.date) ?? { date: p.date };
        row[s.name] = p.value;
        byDate.set(p.date, row);
      }
    }
    const rows = [...byDate.values()].sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    );
    const keys = plottable.map((s) => s.name);
    return normalised ? rebase(rows, keys) : rows;
  }, [data, plottable, normalised, interval]);

  const span = combined.length;

  return (
    <div>
      <SectionTitle hint={hint}>{title}</SectionTitle>

      {error ? (
        <ErrorNote message={`Could not load ${endpoint}: ${error.message}`} />
      ) : null}

      <Card>
        <CardHeader
          title={normalised ? "Rebased to 100 at the start of the range" : `Last ${rangeLabel(range)}`}
          subtitle={
            normalised
              ? "Same starting point for every line, so relative moves are directly comparable."
              : "Each series on its own scale."
          }
          actions={
            <>
              <IntervalSwitch value={interval} onChange={setInterval} />
              <Switch
                checked={showMA50}
                onChange={setShowMA50}
                label="50 MA"
              />
              <Switch
                checked={showMA150}
                onChange={setShowMA150}
                label="150 MA"
              />
              <Switch
                checked={normalised}
                onChange={setNormalised}
                label="Normalised"
              />
            </>
          }
        />

        {isLoading && !data ? <ChartSkeleton height={260} /> : null}
        {data && !plottable.length ? (
          <EmptyNote>
            Nothing to plot for this range yet — these tickers returned no data.
            Check the Data status panel.
          </EmptyNote>
        ) : null}

        {data && combined.length > 0 && normalised ? (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={combined} margin={{ top: 10, right: 14, bottom: 0, left: -4 }}>
              <CartesianGrid stroke={c.line} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(v) => axisDate(v, span)}
                tick={{ fill: c.faint, fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: c.line }}
                minTickGap={44}
              />
              <YAxis
                tick={{ fill: c.faint, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={58}
                domain={["dataMin - 2", "dataMax + 2"]}
                tickFormatter={(v: number) => v.toFixed(0)}
              />
              <Tooltip
                content={
                  <ChartTooltip
                    formats={Object.fromEntries(
                      plottable.map((s) => [s.name, (v: number) => v.toFixed(1)]),
                    )}
                  />
                }
                cursor={{ stroke: c.faint, strokeDasharray: "3 3" }}
              />
              <Legend
                verticalAlign="top"
                align="left"
                height={28}
                iconType="plainline"
                wrapperStyle={{ fontSize: 12, color: c.muted }}
              />
              {plottable.map((s, i) => (
                <Line
                  key={s.name}
                  type="monotone"
                  dataKey={s.name}
                  stroke={colours[i % colours.length]}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : null}

        {data && !normalised ? (
          <div className="grid gap-4 md:grid-cols-3">
            {data.series.map((s, i) => {
              const colour = colours[i % colours.length];
              return (
                <SeriesChartCard
                  key={s.ticker}
                  series={s}
                  colour={colour}
                  interval={interval}
                  showMA50={showMA50}
                  showMA150={showMA150}
                  decimals={decimals}
                  rsOn={rsOn}
                  rsBenchData={rsBenchData}
                  c={c}
                />
              );
            })}
          </div>
        ) : null}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function IntervalSwitch({
  value,
  onChange,
}: {
  value: Interval;
  onChange: (v: Interval) => void;
}) {
  const opts: { key: Interval; label: string }[] = [
    { key: "D", label: "D" },
    { key: "W", label: "W" },
    { key: "M", label: "M" },
  ];
  return (
    <div className="flex items-center gap-0.5 rounded-xl border border-line/80 bg-surface p-0.5 text-[11.5px]">
      {opts.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`rounded-[10px] px-2 py-0.5 font-medium transition ${
            value === o.key
              ? "bg-accent/15 text-accent"
              : "text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function PeriodStat({ label, value }: { label: string; value: number | null }) {
  if (value === null || value === undefined) {
    return (
      <div>
        <p className="text-[9.5px] font-semibold uppercase tracking-wide text-faint">
          {label}
        </p>
        <p className="mt-0.5 text-[11.5px] text-muted">—</p>
      </div>
    );
  }
  const up = value >= 0;
  const colour = `var(--color-${up ? "up" : "down"})`;
  return (
    <div>
      <p className="text-[9.5px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </p>
      <p className="mt-0.5 text-[11.5px] font-semibold" style={{ color: colour }}>
        {signed(value, 1, "%")}
      </p>
    </div>
  );
}

function unitHint(unit: string): string {
  switch (unit) {
    case "USD/oz":
    case "USD/bbl":
      return unit;
    case "₹ per $":
      return "₹/$";
    case "bps":
      return "bps";
    case "index":
      return "";
    default:
      return "";
  }
}

function rangeLabel(range: RangeKey): string {
  return { "1M": "month", "3M": "3 months", "6M": "6 months", "1Y": "year", "3Y": "3 years", "5Y": "5 years" }[range];
}

/** Aggregate daily bars to weekly (last bar per ISO week) or monthly. */

/**
 * Individual series chart card - extracted to fix React hooks violation.
 * This component handles a single series chart with proper hook usage.
 */
function SeriesChartCard({
  series,
  colour,
  interval,
  showMA50,
  showMA150,
  decimals,
  rsOn,
  rsBenchData,
  c,
}: {
  series: SeriesResponse["series"][0];
  colour: string;
  interval: Interval;
  showMA50: boolean;
  showMA150: boolean;
  decimals: number;
  rsOn?: boolean;
  rsBenchData?: { points: { date: string; value: number | null }[]; name: string } | null;
  c: ReturnType<typeof useThemeColors>;
}) {
  const unitLabel = unitHint(series.unit);
  
  // Build chart data with MAs merged in - this hook is now at the top level
  const chartData = useMemo(() => {
    if (!hasFinite(series.points, "value")) return [];
    
    // Build daily data with MAs
    const dailyWithMA: Array<{date: string; value: number | null; ma50?: number | null; ma150?: number | null}> = 
      series.points.map((p, idx) => {
        const row: any = { date: p.date, value: p.value };
        // Always add MA fields when toggles are enabled, even if backend didn't return data
        // This ensures the Line components have data keys to bind to
        if (showMA50) {
          row.ma50 = series.moving_averages?.ma50?.[idx] ?? null;
        }
        if (showMA150) {
          row.ma150 = series.moving_averages?.ma150?.[idx] ?? null;
        }
        return row;
      });
    
    // CORRECT ORDER: aggregate first, then thin for rendering
    const aggregated = aggregate(dailyWithMA, interval);
    return thin(aggregated, 520);
  }, [series.points, series.moving_averages, showMA50, showMA150, interval]);
  
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <p className="truncate text-[12.5px] font-semibold text-ink">
          {series.name}
        </p>
        <span className={`text-[11.5px] font-medium ${toneClass(series.change_pct)}`}>
          {signed(series.change_pct, 1, "%")}
        </span>
      </div>
      <p className="mb-1 flex items-baseline gap-1 font-mono text-[17px] font-semibold tracking-[-0.02em] text-ink">
        {num(series.last_value, decimals)}
        {unitLabel ? (
          <span className="text-[10.5px] font-medium text-faint">
            {unitLabel}
          </span>
        ) : null}
      </p>
      {chartData.length ? (
        <ResponsiveContainer width="100%" height={168}>
          <AreaChart
            data={chartData}
            margin={{ top: 6, right: 8, bottom: 0, left: -18 }}
          >
            <defs>
              <linearGradient id={`fill-${series.ticker.replace(/[^a-zA-Z0-9]/g, "_")}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colour} stopOpacity={0.22} />
                <stop offset="100%" stopColor={colour} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={c.line} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => axisDate(v, chartData.length)}
              tick={{ fill: c.faint, fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: c.line }}
              minTickGap={34}
            />
            <YAxis
              domain={["dataMin - 2", "dataMax + 2"]}
              tick={{ fill: c.faint, fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={58}
              tickFormatter={(v: number) =>
                v.toLocaleString(undefined, { maximumFractionDigits: 1 })
              }
            />
            <Tooltip
              content={
                <ChartTooltip
                  formats={{ value: (v) => num(v, decimals) }}
                />
              }
              cursor={{ stroke: c.faint, strokeDasharray: "3 3" }}
            />
            <Area
              type="monotone"
              dataKey="value"
              name={series.name}
              stroke={colour}
              strokeWidth={1.7}
              fill={`url(#fill-${series.ticker.replace(/[^a-zA-Z0-9]/g, "_")})`}
              dot={false}
              isAnimationActive={false}
              connectNulls
              activeDot={{ r: 3, fill: colour, stroke: withAlpha(colour, 0.3), strokeWidth: 4 }}
            />
            {showMA50 ? (
              <Line
                type="monotone"
                dataKey="ma50"
                name="50 MA"
                stroke={withAlpha(c.ink, 0.55)}
                strokeWidth={1.2}
                dot={false}
                strokeDasharray="3 3"
                isAnimationActive={false}
                connectNulls
              />
            ) : null}
            {showMA150 ? (
              <Line
                type="monotone"
                dataKey="ma150"
                name="150 MA"
                stroke={withAlpha(c.ink, 0.35)}
                strokeWidth={1.2}
                dot={false}
                strokeDasharray="2 4"
                isAnimationActive={false}
                connectNulls
              />
            ) : null}
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-[168px] items-center justify-center rounded-lg border border-dashed border-line text-center text-[11.5px] text-muted">
          No data returned for {series.ticker}
        </div>
      )}

      {/* 1M / 1Y / 5Y period changes */}
      <div className="mt-1 grid grid-cols-3 gap-1.5 border-t border-line/60 pt-2 text-center font-mono">
        <PeriodStat label="1M" value={series.change_1m} />
        <PeriodStat label="1Y" value={series.change_1y} />
        <PeriodStat label="5Y" value={series.change_5y} />
      </div>

      {rsOn && rsBenchData && hasFinite(series.points, "value") ? (
        <div className="mt-2 rounded-lg border border-line/60 bg-canvas/50 p-2">
          <RsSubchart
            rs={computeRS(series.points, rsBenchData.points)}
            c={c}
            height={100}
            benchmarkName={rsBenchData.name}
          />
        </div>
      ) : null}
      {series.note ? (
        <p className="mt-1 text-[11px] leading-snug text-faint">{series.note}</p>
      ) : null}
    </div>
  );
}




