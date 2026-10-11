/** Panel 2 - % of stocks above their 200-day moving average. */

import { useMemo, useState } from "react";
import useSWR from "swr";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BreadthResponse, RangeKey } from "../lib/api";
import { fetcher } from "../lib/api";
import { axisDate, mediumDate, num, signed, thin } from "../lib/format";
import {
  Card,
  CardHeader,
  ChartSkeleton,
  EmptyNote,
  ErrorNote,
  Footnote,
  Pill,
  Segmented,
  Switch,
} from "./ui";
import { ChartTooltip, useThemeColors, withAlpha } from "./charts";

type Mode = "pct" | "ratio";

export function BreadthPanel({
  range,
  theme,
}: {
  range: RangeKey;
  theme: string;
}) {
  const { data, error, isLoading } = useSWR<BreadthResponse>(
    `/api/breadth?range=${range}`,
    fetcher,
    { keepPreviousData: true },
  );
  const [mode, setMode] = useState<Mode>("pct");
  const [showIndex, setShowIndex] = useState(true);
  const c = useThemeColors(theme);

  const rows = useMemo(() => {
    if (!data) return [];
    const indexByDate = new Map(data.index.map((p) => [p.date, p.close]));
    return thin(
      data.points.map((p) => ({
        date: p.date,
        value: mode === "pct" ? p.pct_above : p.above_below,
        index: indexByDate.get(p.date) ?? null,
        n_above: p.n_above,
        n_valid: p.n_valid,
      })),
    );
  }, [data, mode]);

  const hasIndex = Boolean(
    data?.index?.some((p) => typeof p.close === "number" && Number.isFinite(p.close)),
  );
  const overlay = showIndex && hasIndex;

  const latest = data?.latest ?? null;
  const span = rows.length ? rows.length * (range === "1M" ? 1 : 1.4) : 0;
  const valueName = mode === "pct" ? "% above 200DMA" : "Above ÷ below";

  return (
    <Card>
      <CardHeader
        title="Market breadth — stocks above their 200DMA"
        subtitle="The share of the universe in a long-term uptrend. Above 50% is a broad market; the extremes mark washouts and froth."
        actions={
          <>
            <Segmented<Mode>
              size="sm"
              ariaLabel="Breadth display"
              value={mode}
              onChange={setMode}
              options={[
                { value: "pct", label: "% above" },
                { value: "ratio", label: "Above / below" },
              ]}
            />
            {hasIndex ? (
              <Switch
                checked={showIndex}
                onChange={setShowIndex}
                label={data?.index_name ?? "Index"}
              />
            ) : null}
          </>
        }
      />

      {error ? <ErrorNote message={`Could not load breadth: ${error.message}`} /> : null}
      {isLoading && !data ? <ChartSkeleton height={320} /> : null}

      {data && !data.points.length ? (
        <EmptyNote>
          No breadth data for this range yet — run a refresh to download prices.
        </EmptyNote>
      ) : null}

      {data && data.points.length ? (
        <div className="grid gap-5 lg:grid-cols-[210px_1fr]">
          <div className="flex flex-col justify-center gap-3 lg:border-r lg:border-line lg:pr-5">
            {latest ? (
              <>
                <div>
                  <p className="text-[11.5px] uppercase tracking-[0.08em] text-faint">
                    Today’s reading
                  </p>
                  <p className="mt-1 flex items-baseline gap-1 font-mono text-[40px] font-semibold leading-none tracking-[-0.03em] text-ink">
                    {latest.pct_above === null ? "—" : latest.pct_above.toFixed(1)}
                    <span className="text-[18px] font-medium text-muted">%</span>
                  </p>
                  <p className="mt-1 text-[12px] text-muted">
                    {mediumDate(latest.date)}
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <Pill
                    tone={
                      (latest.change_1d ?? 0) > 0
                        ? "up"
                        : (latest.change_1d ?? 0) < 0
                          ? "down"
                          : "neutral"
                    }
                  >
                    {signed(latest.change_1d, 1, " pt")} · 1d
                  </Pill>
                  <Pill
                    tone={
                      (latest.change_1w ?? 0) > 0
                        ? "up"
                        : (latest.change_1w ?? 0) < 0
                          ? "down"
                          : "neutral"
                    }
                  >
                    {signed(latest.change_1w, 1, " pt")} · 1w
                  </Pill>
                </div>

                <div>
                  <div className="flex h-2 overflow-hidden rounded-full bg-line">
                    <div
                      className="h-full rounded-l-full bg-up transition-all duration-500"
                      style={{ width: `${latest.pct_above ?? 0}%` }}
                    />
                    <div className="h-full flex-1 bg-down/70" />
                  </div>
                  <p className="mt-1.5 text-[11.5px] text-muted">
                    <span className="font-medium text-ink">{latest.n_above}</span> above ·{" "}
                    <span className="font-medium text-ink">{latest.n_below}</span> below ·{" "}
                    {latest.n_valid} with a valid 200DMA
                  </p>
                </div>
              </>
            ) : null}
          </div>

          <div>
            <ResponsiveContainer width="100%" height={330}>
              <ComposedChart
                data={rows}
                margin={{ top: 6, right: overlay ? 4 : 10, bottom: 0, left: -10 }}
              >
                {mode === "pct" ? (
                  <>
                    <ReferenceArea
                      y1={data.thresholds.overbought}
                      y2={100}
                      yAxisId="left"
                      fill={withAlpha(c.down, 0.06)}
                      stroke="none"
                    />
                    <ReferenceArea
                      y1={0}
                      y2={data.thresholds.oversold}
                      yAxisId="left"
                      fill={withAlpha(c.up, 0.07)}
                      stroke="none"
                    />
                  </>
                ) : null}
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
                  yAxisId="left"
                  domain={mode === "pct" ? [0, 100] : ["auto", "auto"]}
                  ticks={mode === "pct" ? [0, 20, 50, 80, 100] : undefined}
                  tick={{ fill: c.faint, fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                />
                {overlay ? (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    domain={["auto", "auto"]}
                    tick={{ fill: c.faint, fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={52}
                    tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  />
                ) : null}

                {mode === "pct" ? (
                  <>
                    <ReferenceLine
                      yAxisId="left"
                      y={data.thresholds.midline}
                      stroke={c.faint}
                      strokeDasharray="4 4"
                    />
                    <ReferenceLine
                      yAxisId="left"
                      y={data.thresholds.overbought}
                      stroke={withAlpha(c.down, 0.5)}
                      strokeDasharray="2 5"
                    />
                    <ReferenceLine
                      yAxisId="left"
                      y={data.thresholds.oversold}
                      stroke={withAlpha(c.up, 0.5)}
                      strokeDasharray="2 5"
                    />
                  </>
                ) : (
                  <ReferenceLine
                    yAxisId="left"
                    y={1}
                    stroke={c.faint}
                    strokeDasharray="4 4"
                  />
                )}

                <Tooltip
                  content={
                    <ChartTooltip
                      formats={{
                        value: (v) => (mode === "pct" ? `${v.toFixed(1)}%` : num(v, 2)),
                        index: (v) => num(v, 0),
                      }}
                    />
                  }
                  cursor={{ stroke: c.faint, strokeDasharray: "3 3" }}
                />

                {overlay ? (
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="index"
                    name={data.index_name}
                    stroke={c.neutral}
                    strokeWidth={1.3}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                ) : null}
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="value"
                  name={valueName}
                  stroke={c.accent}
                  strokeWidth={1.9}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}

      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-[2px] w-4 rounded"
            style={{ background: c.accent }}
          />
          % above 200DMA
        </span>
        {overlay ? (
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-[2px] w-4 rounded"
              style={{ background: c.neutral, opacity: 0.7 }}
              aria-hidden
            />
            <span
              className="inline-block h-[2px] w-4 rounded"
              style={{
                background: `repeating-linear-gradient(to right, ${c.neutral} 0 4px, transparent 4px 8px)`,
              }}
            />
            {data?.index_name}
          </span>
        ) : null}
      </div>

      <Footnote>
        Denominator is the number of stocks with a valid 200-day average that day, so
        recent listings never distort the reading. {data?.footnote}
      </Footnote>
    </Card>
  );
}
